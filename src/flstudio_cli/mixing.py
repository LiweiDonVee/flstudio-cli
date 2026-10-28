"""Saved mixer controls and complete, state-preserving effect chains."""
from __future__ import annotations

import math
import struct

from .flp import Event, Project


PLUGIN_EVENTS = {201, 203, 212, 213, 155, 128, 41}
TRACK_FLAGS = {'polarity_reversed': (1, True), 'channels_swapped': (2, True),
               'threaded_processing': (16, False), 'solo': (0x1000, True)}
EQ_CONTROLS = {'gain_raw': (208, -1800, 1800), 'frequency_raw': (216, 0, 65536),
               'bandwidth_raw': (224, 0, 65536)}


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
        if address & 0xffff == 0x1fc0 and (address >> 16) & 0xffc0 == selector:
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
        for name, (mask, positive) in TRACK_FLAGS.items():
            track[name] = bool(flags & mask) == positive if flags is not None else None
        block = {e.id: e for e in project.events[start:end]}
        for name, eid in (('hardware_output_raw', 147), ('hardware_input_raw', 154)):
            track[name] = struct.unpack_from('<i', block[eid].data)[0] if eid in block else None
        track['eq'] = [{'band': band, **{name: values.get(base | (ident + band))
                        for name, (ident, _, _) in EQ_CONTROLS.items()}} for band in range(3)]
        track['sends'] = [{'to': destination, 'level': values.get(send_address(project, track['index'], destination), 12800) / 12800}
                          for destination in track['routes']]
        for plugin in track['plugins']:
            address = base | (plugin['slot'] << 16)
            plugin['enabled'] = bool(values.get(address, 1))
            plugin['wet'] = values.get(address | 1, 12800) / 12800
    return tracks


def set_track_field(project, track, key, value):
    start, end = project.mixer_spans()[track]
    block = {e.id: e for e in project.events[start:end]}
    if key in TRACK_FLAGS:
        if type(value) is not bool: raise ValueError(f'{key} must be a boolean')
        data = bytearray(block[236].data); flags = struct.unpack_from('<I', data, 4)[0]
        mask, positive = TRACK_FLAGS[key]
        struct.pack_into('<I', data, 4, flags | mask if value == positive else flags & ~mask)
        block[236].data = bytes(data)
    elif key in ('hardware_input_raw', 'hardware_output_raw'):
        if type(value) is not int or not -0x80000000 <= value <= 0x7fffffff: raise ValueError('Hardware selector requires a signed 32-bit integer')
        eid = 154 if key == 'hardware_input_raw' else 147
        if eid not in block: raise ValueError('Hardware selector is absent in this track')
        block[eid].data = struct.pack('<i', value)
    elif key == 'eq':
        if not isinstance(value, list): raise ValueError('EQ requires an array of explicit band edits')
        base, values = track_address(project, track), initial_values(project)
        for band in value:
            if not isinstance(band, dict) or set(band) - {'band', *EQ_CONTROLS} or type(band.get('band')) is not int or not 0 <= band['band'] < 3: raise ValueError('EQ band must be 0..2 with known raw fields')
            for name, raw in band.items():
                if name == 'band': continue
                ident, low, high = EQ_CONTROLS[name]; address = base | (ident + band['band'])
                if type(raw) is not int or not low <= raw <= high: raise ValueError(f'{name} must be {low}..{high}')
                if address not in values: raise ValueError('EQ host control is absent')
                set_initial(project, address, raw)
    else: raise ValueError('Unknown mixer field')


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


def _fx_control(address):
    return address & 0xffff >= 0x8000 or address & 0xffff in (0x1f00, 0x1f01)


def _slot_controls(project, source, destination, target):
    records = []
    for event in project.events:
        if event.id not in (216, 225): continue
        for at in range(0, len(event.data), 12):
            address = struct.unpack_from('<I', event.data, at + 4)[0]
            if address >> 16 != source >> 16 or not _fx_control(address): continue
            row = bytearray(event.data[at:at + 12])
            struct.pack_into('<I', row, 4, (destination & 0xffff0000) | (address & 0xffff))
            records.append((event.id, row))
    for name, offset, default in (('enabled', 0, 1), ('wet', 1, 12800)):
        address = destination | offset
        matches = [row for _, row in records if struct.unpack_from('<I', row, 4)[0] == address]
        if name in target:
            value = int(target[name]) if name == 'enabled' else round(target[name] * 12800)
            for row in matches: struct.pack_into('<i', row, 8, value)
        else: value = default
        if not matches: records.append((225, bytearray(struct.pack('<IIi', 0, address, value))))
    return records


def _replace_slot_controls(project, base, records):
    for event in project.events:
        if event.id in (216, 225):
            event.data = b''.join(event.data[at:at + 12] for at in range(0, len(event.data), 12)
                if not ((address := struct.unpack_from('<I', event.data, at + 4)[0]) >> 16 == base >> 16 and _fx_control(address)))
    for eid, row in records:
        event = next((e for e in project.events if e.id == eid), None)
        if event is None:
            event = Event(eid, b'')
            at = next((i for i, e in enumerate(project.events) if e.id == 64), len(project.events))
            project.events.insert(at, event)
        event.data += bytes(row)


def _chain_links(project, edited_tracks, copies, destinations):
    affected = {slot_address(project, track, plugin['slot']) >> 16
                for track in edited_tracks for plugin in project.mixer()[track]['plugins']}
    affected.update(destinations)
    def mapped(address):
        group = address >> 16
        if group not in affected or not _fx_control(address): return address
        options = copies.get(group, [])
        if group in options: return address
        if len(options) != 1:
            raise ValueError('A linked effect is removed or copied to ambiguous destinations; retain its slot or unlink it first')
        return options[0] << 16 | (address & 0xffff)
    changes = []
    for event in project.events:
        if event.id == 227 and event.data:
            if len(event.data) != 20: raise ValueError('Unsupported controller-link record layout')
            for at in (0, 8):
                address = struct.unpack_from('<I', event.data, at)[0]
                updated = mapped(address)
                if address != updated: changes.append((event, at, updated))
        elif event.id == 223:
            if len(event.data) % 12: raise ValueError('Unsupported pattern-controller record layout')
            for at in range(4, len(event.data), 12):
                address = struct.unpack_from('<I', event.data, at)[0]
                updated = mapped(address)
                if address != updated: changes.append((event, at, updated))
    return changes


def apply_chains(project: Project, chains: list[dict]) -> None:
    if not isinstance(chains, list):
        raise ValueError('fx_chains must be an array')
    if not chains:
        return
    snapshot = Project(project.encode())
    tracks_seen, prepared, copies = set(), [], {}
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
            if ('enabled' in target and type(target['enabled']) is not bool or 'wet' in target and
                (type(target['wet']) not in (int, float) or not math.isfinite(target['wet']) or not 0 <= target['wet'] <= 1)):
                raise ValueError('Slot enabled must be boolean and wet must be finite 0..1')
            if 'copy_from' in target:
                source = target['copy_from']
                if not isinstance(source, dict) or set(source) != {'track', 'slot'}:
                    raise ValueError('copy_from requires track and slot')
                events = snapshot.effect_events(source['track'], source['slot'])
                old_base = slot_address(snapshot, source['track'], source['slot'])
                controls = _slot_controls(snapshot, old_base, base, target)
                copies.setdefault(old_base >> 16, []).append(base >> 16)
            else:
                from .flp import preset_events
                events = preset_events(target['preset'])
                controls = [(225, struct.pack('<IIi', 0, base, int(target.get('enabled', True)))),
                            (225, struct.pack('<IIi', 0, base | 1, round(target.get('wet', 1.0) * 12800)))]
            targets.append((slot, events, controls))
        prepared.append((track, targets))
    link_changes = _chain_links(project, tracks_seen, copies,
        {slot_address(project, track, slot) >> 16 for track, targets in prepared for slot, _, _ in targets})
    # Resolve every source before removing anything, so moves/swaps across
    # multiple tracks retain their exact state regardless of request order.
    for track, targets in prepared:
        for slot in range(10):
            start, end = _slot_span(project, track, slot)
            project.events[start:end] = [e for e in project.events[start:end] if e.id not in PLUGIN_EVENTS]
            base = slot_address(project, track, slot)
            _replace_slot_controls(project, base, [(225, struct.pack('<IIi', 0, base, 1)),
                                                 (225, struct.pack('<IIi', 0, base | 1, 12800))])
        for slot, events, controls in targets:
            project.load_effect(track, slot, events, links_prepared=True)
            base = slot_address(project, track, slot)
            _replace_slot_controls(project, base, controls)
    # Slot edits retain the actual controller/link Event objects.
    for event, offset, address in link_changes:
        data = bytearray(event.data); struct.pack_into('<I', data, offset, address); event.data = bytes(data)


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
