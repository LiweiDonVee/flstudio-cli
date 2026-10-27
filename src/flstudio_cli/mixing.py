"""Saved mixer controls and complete, state-preserving effect chains."""
from __future__ import annotations

import math
import struct

from .flp import Event, Project


PLUGIN_EVENTS = {201, 203, 212, 213, 155, 128, 41}


def initial_values(project: Project) -> dict[int, int]:
    values = {}
    # Start controls take precedence when FL begins playback.
    for eid in (225, 216):
        for event in project.events:
            if event.id == eid:
                if len(event.data) % 12:
                    raise ValueError('Unsupported initial-control record layout')
                for offset in range(0, len(event.data), 12):
                    address, value = struct.unpack_from('<Ii', event.data, offset + 4)
                    values[address] = value
    return values


def set_initial(project: Project, address: int, value: int, *, event_id=225):
    found = False
    for event in project.events:
        if event.id not in (216, 225):
            continue
        if len(event.data) % 12:
            raise ValueError('Unsupported initial-control record layout')
        data = bytearray(event.data)
        for offset in range(0, len(data), 12):
            if struct.unpack_from('<I', data, offset + 4)[0] == address:
                struct.pack_into('<i', data, offset + 8, value)
                found = True
        event.data = bytes(data)
    if not found:
        event = next((e for e in project.events if e.id == event_id), None)
        if event is None:
            event = Event(event_id, b'')
            # Initial controls belong before the channel sections, not inside one.
            at = next((i for i, e in enumerate(project.events) if e.id == 64), len(project.events))
            project.events.insert(at, event)
        event.data += struct.pack('<IIi', 0, address, value)


def track_address(project: Project, track: int) -> int:
    if type(track) is not int or not 0 <= track < len(project.mixer_spans()) - 1:
        raise ValueError('Choose an ordinary saved mixer track, including Master 0')
    selector = next((s for s, t in project._mixer_selectors().items() if t == track), None)
    if selector is None:
        raise ValueError('Mixer track has no known host control address')
    for address in initial_values(project):
        if address & 255 == 192 and (address >> 16) & 0xffc0 == selector:
            return address & 0xffffff00
    raise ValueError('Mixer volume control is absent')


def slot_address(project: Project, track: int, slot: int) -> int:
    if type(slot) is not int or not 0 <= slot < 10:
        raise ValueError('Effect slot must be 0..9')
    return track_address(project, track) | (slot << 16)


def send_address(project: Project, track: int, destination: int) -> int:
    base = track_address(project, track)
    # The 500-insert format moved sends out of the old 128-send general
    # property range. Factory FL25/26 files use 0x2000 + destination.
    if base >> 16 >= 0x7000:
        return (base & 0xffff0000) | (0x2000 + destination)
    return base | (64 + destination)


def describe_mixer(project: Project, tracks: list[dict]):
    values = initial_values(project)
    for track in tracks[:-1]:
        base = track_address(project, track['index'])
        for name, ident in (('volume_raw', 192), ('pan_raw', 193)):
            if base | ident in values:
                track[name] = values[base | ident]
        start, end = project.mixer_spans()[track['index']]
        flags = next((struct.unpack_from('<I', e.data, 4)[0] for e in project.events[start:end]
                      if e.id == 236 and len(e.data) >= 8), None)
        track['muted'] = not bool(flags & 8) if flags is not None else None
        track['effects_enabled'] = bool(flags & 4) if flags is not None else None
        track['sends'] = [{'to': destination, 'level': values.get(send_address(project, track['index'], destination), 12800) / 12800}
                          for destination in track['routes']]
        for plugin in track['plugins']:
            address = base | (plugin['slot'] << 16)
            plugin['enabled'] = bool(values.get(address, 1))
            plugin['wet'] = values.get(address | 1, 12800) / 12800
    return tracks


def set_sends(project: Project, track: int, sends: list[dict]):
    if not isinstance(sends, list):
        raise ValueError('sends must be an array of {to, level}; zero means a sidechain-only route')
    seen = set()
    for send in sends:
        if not isinstance(send, dict) or set(send) != {'to', 'level'}:
            raise ValueError('Each send requires exactly to and level')
        destination, level = send['to'], send['level']
        if (type(destination) is not int or not 0 <= destination < len(project.mixer_spans()) - 1
                or destination == track or destination in seen):
            raise ValueError('Send destinations must be unique existing tracks other than the source')
        if type(level) not in (int, float) or not math.isfinite(level) or not 0 <= level <= 1:
            raise ValueError('Send level must be finite, 0..1 (1 = unity)')
        seen.add(destination)
    # An explicit send also enables its route. Omitted destinations are retained;
    # use routes to specify the complete destination set.
    routes = project.mixer()[track]['routes']
    project.set_mixer(track, {'routes': sorted(set(routes) | seen)})
    for send in sends:
        set_initial(project, send_address(project, track, send['to']), round(send['level'] * 12800))


def _slot_span(project: Project, track: int, slot: int):
    slot_address(project, track, slot)
    start, end = project.mixer_spans()[track]
    position = start
    for index in range(start, end):
        if project.events[index].id == 98:
            if int.from_bytes(project.events[index].data, 'little') == slot:
                return position, index
            position = index + 1
    raise ValueError('Effect slot is absent from this mixer profile')


def _erase_plugin_controls(project: Project, base: int):
    group = base >> 16
    for event in project.events:
        if event.id in (216, 225):
            event.data = b''.join(event.data[o:o + 12] for o in range(0, len(event.data), 12)
                                  if not ((struct.unpack_from('<I', event.data, o + 4)[0] >> 16) == group
                                          and struct.unpack_from('<H', event.data, o + 4)[0] >= 0x8000))


def apply_chains(project: Project, chains: list[dict]) -> None:
    if not isinstance(chains, list):
        raise ValueError('fx_chains must be an array')
    if not chains:
        return
    # Slot references inside automation/controllers need their own adapter.
    if any(e.id in (227, 234) and e.data for e in project.events):
        raise ValueError('FX chain replacement with controller/automation links is not supported; keep the linked chain in GUI')
    snapshot = Project(project.encode())
    old_values = initial_values(snapshot)
    tracks_seen, prepared = set(), []
    for chain in chains:
        if not isinstance(chain, dict) or set(chain) != {'track', 'slots'} or not isinstance(chain['slots'], list):
            raise ValueError('Each fx_chains entry requires track and complete slots array')
        track = chain['track']
        track_address(project, track)
        if track in tracks_seen:
            raise ValueError('Each target FX chain may be specified once')
        tracks_seen.add(track)
        slots_seen, targets = set(), []
        for target in chain['slots']:
            if (not isinstance(target, dict) or set(target) - {'slot', 'preset', 'copy_from', 'enabled', 'wet'}
                    or 'slot' not in target or ('preset' in target) == ('copy_from' in target)):
                raise ValueError('Each slot requires slot and exactly one preset or copy_from; optional enabled/wet')
            slot = target['slot']
            base = slot_address(project, track, slot)
            if slot in slots_seen:
                raise ValueError('Duplicate target effect slot')
            slots_seen.add(slot)
            controls = []
            if 'copy_from' in target:
                source = target['copy_from']
                if not isinstance(source, dict) or set(source) != {'track', 'slot'}:
                    raise ValueError('copy_from requires track and slot')
                events = snapshot.effect_events(source['track'], source['slot'])
                old_base = slot_address(snapshot, source['track'], source['slot'])
                enabled = bool(old_values.get(old_base, 1))
                wet = old_values.get(old_base | 1, 12800) / 12800
                for address, value in old_values.items():
                    if address >> 16 == old_base >> 16 and address & 0xffff >= 0x8000:
                        controls.append((225, (base & 0xffff0000) | (address & 0xffff), value))
            else:
                from .flp import preset_events
                events = preset_events(target['preset'])
                enabled, wet = True, 1.0
            enabled, wet = target.get('enabled', enabled), target.get('wet', wet)
            if type(enabled) is not bool or type(wet) not in (int, float) or not math.isfinite(wet) or not 0 <= wet <= 1:
                raise ValueError('Slot enabled must be boolean and wet must be finite 0..1')
            targets.append((slot, events, enabled, wet, controls))
        prepared.append((track, targets))
    # Resolve every source before removing anything, so moves/swaps across
    # multiple tracks retain their exact state regardless of request order.
    for track, targets in prepared:
        for slot in range(10):
            start, end = _slot_span(project, track, slot)
            project.events[start:end] = [e for e in project.events[start:end] if e.id not in PLUGIN_EVENTS]
            base = slot_address(project, track, slot)
            _erase_plugin_controls(project, base)
            set_initial(project, base, 1)
            set_initial(project, base | 1, 12800)
        for slot, events, enabled, wet, controls in targets:
            project.load_effect(track, slot, events)
            base = slot_address(project, track, slot)
            set_initial(project, base, int(enabled))
            set_initial(project, base | 1, round(wet * 12800))
            for eid, address, value in controls:
                set_initial(project, address, value, event_id=eid)


def validate_routing(project: Project):
    graph = {track['index']: [s['to'] for s in track.get('sends', []) if s['level'] > 0]
             for track in project.mixer()[:-1]}
    visiting, visited = set(), set()
    def visit(track):
        if track in visiting:
            raise ValueError('Mixer sends form an audio-feedback cycle')
        if track in visited:
            return
        visiting.add(track)
        for destination in graph[track]:
            visit(destination)
        visiting.remove(track)
        visited.add(track)
    for track in graph:
        visit(track)
