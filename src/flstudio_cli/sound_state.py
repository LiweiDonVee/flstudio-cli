"""Transfer complete saved channel timbres without transplanting score identity."""
from __future__ import annotations

from pathlib import Path
import struct

from .flp import Event, Project
from .mixing import initial_values, slot_address, _slot_controls, _replace_slot_controls, _fx_control

# Keep the receiving channel's musical identity and routing. Everything else
# in the channel, including opaque plugin state and sampler envelopes, moves.
IDENTITY = {64, 203, 128, 22, 104, 0}


def channel_events(project, channel):
    if type(channel) is not int or not 0 <= channel < len(project.channel_spans()):
        raise ValueError('Choose an existing saved generator channel')
    a, b = project.channel_spans()[channel]
    return project.events[a:b]


def controls(project, group):
    return {address & 0xffff: value for address, value in initial_values(project).items()
            if address >> 16 == group}


def state_view(project, channel, include_fx=True):
    info = project.channels()[channel]
    result = {'events': [(e.id, e.data.hex()) for e in channel_events(project, channel) if e.id not in IDENTITY],
              'controls': controls(project, info['iid'])}
    if include_fx:
        track = info['mixer_track']
        result['effects'] = [{'slot': p['slot'], 'events': [(e.id, e.data.hex()) for e in project.effect_events(track, p['slot'])],
                              'controls': {key:value for key,value in controls(project, slot_address(project, track, p['slot']) >> 16).items() if _fx_control(key)}}
                             for p in project.mixer()[track]['plugins']]
    return result


def _replace_channel_controls(destination, dest_iid, source, source_iid):
    rows = []
    for event in source.events:
        if event.id not in (216, 225):
            continue
        for at in range(0, len(event.data), 12):
            address = struct.unpack_from('<I', event.data, at+4)[0]
            if address >> 16 == source_iid:
                row = bytearray(event.data[at:at+12])
                struct.pack_into('<I', row, 4, dest_iid << 16 | address & 0xffff)
                rows.append((event.id, bytes(row)))
    for event in destination.events:
        if event.id in (216, 225):
            event.data = b''.join(event.data[at:at+12] for at in range(0, len(event.data), 12)
                                  if struct.unpack_from('<I', event.data, at+4)[0] >> 16 != dest_iid)
    for ident, row in rows:
        event = next((e for e in destination.events if e.id == ident), None)
        if event is None:
            event = Event(ident, b'')
            at = next((i for i, e in enumerate(destination.events) if e.id == 64), len(destination.events))
            destination.events.insert(at, event)
        event.data += row


def exclusive_insert(project, channel):
    info = project.channels()[channel]
    track = info['mixer_track']
    if track == 0 or any(c['index'] != channel and c['mixer_track'] == track for c in project.channels()):
        return False
    return not any(t['index'] != track and track in t['routes'] for t in project.mixer()[:-1])


def check_plugin_bindings(project,channel,other_info):
    # Parameter automation is an external reference to the original plugin.
    # Replacing its parameter layout would silently repurpose the composition.
    from .automation import read_all
    def plugin_identity(info):
        wrapped=info.get('wrapped_plugin') or {}
        return info['plugin'],wrapped.get('class_id_hex'),wrapped.get('name')
    info=project.channels()[channel]
    if plugin_identity(info) != plugin_identity(other_info) and any(
            address >> 16 == info['iid'] and address & 0xffff >= 0x8000
            for curve in read_all(project) for address in curve.get('target_addresses', [])):
        raise ValueError('Existing automation targets this generator; retain its plugin or explicitly rebind the automation in a separate edit')


def transfer(destination, dest_channel, source, source_channel, include_fx=True):
    dest_info, source_info = destination.channels()[dest_channel], source.channels()[source_channel]
    if include_fx and not exclusive_insert(destination, dest_channel):
        raise ValueError('The target insert is shared or Master; transfer the channel only, or assign a dedicated insert first')
    if source_info['type'] not in (0, 2):
        raise ValueError('Sound transfer currently supports generator or sampler channels, not Audio/Automation/Layer channels')
    check_plugin_bindings(destination,dest_channel,source_info)
    original = {e.id: Event(e.id, e.data) for e in channel_events(destination, dest_channel) if e.id in IDENTITY}
    replacement, emitted = [], set()
    for event in channel_events(source, source_channel):
        if event.id in IDENTITY:
            if event.id in original and event.id not in emitted:
                replacement.append(original[event.id]); emitted.add(event.id)
        else:
            replacement.append(Event(event.id, event.data))
    for ident, event in original.items():
        if ident not in emitted:
            replacement.append(event)
    a, b = destination.channel_spans()[dest_channel]
    destination.events[a:b] = replacement
    _replace_channel_controls(destination, dest_info['iid'], source, source_info['iid'])
    if include_fx:
        # Resolve source bytes and controls before clearing the receiving slots.
        source_track, dest_track = source_info['mixer_track'], dest_info['mixer_track']
        rows = []
        for plugin in source.mixer()[source_track]['plugins']:
            slot = plugin['slot']
            source_base, dest_base = slot_address(source, source_track, slot), slot_address(destination, dest_track, slot)
            rows.append((slot, source.effect_events(source_track, slot), _slot_controls(source, source_base, dest_base, {})))
        from .mixing import apply_chains
        apply_chains(destination, [{'track': dest_track, 'slots': []}])
        for slot, events, values in rows:
            destination.load_effect(dest_track, slot, events)
            _replace_slot_controls(destination, slot_address(destination, dest_track, slot), values)
    if destination.patterns() != Project(destination.source).patterns():
        raise ValueError('Sound transfer unexpectedly changed score records')
    return {'channel': dest_channel, 'channel_iid': dest_info['iid'], 'mixer_track': dest_info['mixer_track'],
            'preserved': ['channel identity/name/color/mute/routing', 'all scores', 'other channels', 'Playlist', 'other Mixer inserts'],
            'scope': 'Complete channel events and saved controls' + (' plus dedicated insert FX states/overrides' if include_fx else '')}


def resources(project, source_dir=None):
    """Known channel assets plus opaque-resource disclosure, not a false inventory."""
    rows = []
    for channel in project.channels():
        value = channel.get('sample_path')
        if value:
            path = Path(value)
            if not path.is_absolute() and source_dir:
                path = Path(source_dir)/path
            rows.append({'channel': channel['index'], 'kind': 'channel_sample', 'declared_path': value,
                         'path': str(path.resolve()), 'exists': path.is_file()})
        if channel.get('wrapped_plugin'):
            plugin = channel['wrapped_plugin']
            path = Path(plugin.get('path', ''))
            rows.append({'channel': channel['index'], 'kind': 'plugin_module', 'path': str(path),
                         'exists': path.is_file(), 'plugin': plugin})
    return {'known': rows, 'opaque_plugin_dependencies': 'Plugin-internal sample/wavetable/IR paths cannot be exhaustively enumerated by the generic host API. Declare any external assets used in the candidate request; missing declarations limit portability.'}


def rebase_samples(project, source_dir):
    for channel in project.channels():
        raw = channel.get('sample_path')
        if raw and not Path(raw).is_absolute():
            path = Path(source_dir)/raw
            if not path.is_file():
                raise ValueError(f'Unresolved relative sample {raw!r}; locate the asset before preparing a relocated task')
            project.set_channel(channel['index'], {'sample_path': str(path.resolve())})
