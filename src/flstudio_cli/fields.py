"""Named edits of existing project fields; unknown bytes remain attached."""
from __future__ import annotations

import math
import struct

TEXT = {'title': 194, 'artists': 207, 'genre': 206, 'url': 197, 'comments_text': 195,
        'comments_rtf': 198, 'data_path': 202}
TRACK = {'color': (4, 'I'), 'icon': (8, 'I'), 'enabled': (12, '?'), 'height': (13, 'f'),
         'locked_height': (17, 'i'), 'content_locked': (21, '?'), 'motion_raw': (22, 'I'),
         'press_raw': (26, 'I'), 'trigger_sync_raw': (30, 'I'), 'queued': (34, 'I', 0),
         'tolerant': (38, 'I', 0), 'position_sync_raw': (42, 'I'),
         'grouped': (46, '?'), 'locked': (47, '?')}
SAMPLER = {
    'reverse': (70, 0, 'H', 2), 'swap_stereo': (70, 0, 'H', 256), 'clip': (70, 0, 'H', 4),
    'fade_stereo': (70, 0, 'H', 1), 'loop_points': (143, 0, 'I', 8), 'keep_on_disk': (143, 0, 'I', 256),
    'load_regions': (143, 0, 'I', 2), 'load_slices': (143, 0, 'I', 4), 'resample': (143, 0, 'I', 1),
    'ping_pong_loop': (20, 0, '?'), 'root_note': (135, 0, 'I'), 'event142_raw': (142, 0, 'i'),
    'normalize': (215, 80, '?'), 'inverted': (215, 81, '?'), 'remove_dc': (215, 9, '?'),
    'declick_mode': (215, 83, 'B'), 'crossfade_raw': (215, 84, 'I'), 'trim_raw': (215, 88, 'I'),
    'fade_out_raw': (75, 0, 'H'), 'fade_in_raw': (76, 0, 'H'), 'preamp_raw': (74, 0, 'H'),
    'cutoff_raw': (71, 0, 'H'), 'frequency_tilt_raw': (69, 0, 'H'), 'resonance_raw': (83, 0, 'H'),
    'stereo_delay_raw': (85, 0, 'H'), 'pogo_raw': (86, 0, 'H'), 'reverb_raw': (139, 0, 'I'),
    'ringmod_mix_raw': (131, 0, 'H'), 'ringmod_frequency_raw': (131, 2, 'H'),
    'start_log_word': (215, 133, 'H'), 'start_format_word': (215, 135, 'H'),
    'length_log_word': (215, 141, 'H'), 'length_format_word': (215, 143, 'H'),
    'fix_trim': (215, 157, '?')}
DELAY = {'feedback_raw': (209, 0, 'I'), 'pan_raw': (209, 4, 'i'), 'pitch_cents': (209, 8, 'i'),
         'echoes': (209, 12, 'I'), 'time_raw': (209, 16, 'I'),
         'mod_x_raw': (138, 0, 'H'), 'mod_y_raw': (138, 2, 'H'),
         'ping_pong': (215, 10, 'B', 2), 'fat_mode': (215, 10, 'B', 4)}
FILTER = {'mod_x_raw': (219, 12, 'I'), 'mod_y_raw': (219, 16, 'I'), 'type_raw': (219, 20, 'I')}
LEVEL = {'pan_raw': (229, 0, 'i'), 'volume_raw': (229, 4, 'I'),
         'mod_x_raw': (229, 12, 'i'), 'mod_y_raw': (229, 16, 'i')}
TIME = {'swing_raw': (97, 0, 'H'), 'shift_raw': (89, 0, 'H'), 'gate_raw': (215, 64, 'H')}
KEYBOARD = {'main_pitch': (215, 11, '?'), 'low_note': (215, 68, 'I'), 'high_note': (215, 72, 'I')}
PLAYBACK = {'start_offset_raw': (215, 148, 'I')}
CUT = {'cut_self': (132, 0, 'H'), 'cut_by': (132, 2, 'H')}
LAYER = {'random': (144, 0, 'I', 1), 'crossfade': (144, 0, 'I', 2)}
TRACKING = {'middle_value': (0, 'I'), 'pan_raw': (4, 'i'), 'mod_x_raw': (8, 'i'), 'mod_y_raw': (12, 'i')}
POLY = {'max': (221, 0, 'I'), 'slide_raw': (221, 4, 'I'),
        'mono': (221, 8, 'B', 1), 'porta': (221, 8, 'B', 2)}
ARP = {'direction': (215, 40, 'I'), 'range': (215, 44, 'I'), 'chord': (215, 48, 'I'),
       'time_raw': (215, 52, 'I'), 'gate_raw': (215, 56, 'I'), 'slide': (215, 60, '?'),
       'repeat': (215, 92, 'I'), 'full_porta': (215, 62, '?'), 'add_root': (215, 63, '?')}
STRETCH = {'time_raw': (215, 96, 'I'), 'pitch_cents': (215, 100, 'i'),
           'multiplier_raw': (215, 104, 'i'), 'mode': (215, 108, 'i')}
ENV = {'tempo_sync': (0, 'I', 1), 'lfo_tempo_sync': (0, 'I', 2), 'lfo_retrigger': (0, 'I', 32),
       'enabled': (4, 'i', 0), 'predelay_raw': (8, 'i'), 'attack_raw': (12, 'i'),
       'hold_raw': (16, 'i'), 'decay_raw': (20, 'i'), 'sustain_raw': (24, 'i'),
       'release_raw': (28, 'i'), 'amount_raw': (32, 'i'), 'lfo_predelay_raw': (36, 'I'),
       'lfo_attack_raw': (40, 'I'), 'lfo_amount_raw': (44, 'i'), 'lfo_speed_raw': (48, 'I'),
       'lfo_shape': (52, 'i'), 'attack_tension_raw': (56, 'i'),
       'decay_tension_raw': (60, 'i'), 'release_tension_raw': (64, 'i')}
ENVELOPES = ('panning', 'volume', 'mod_x', 'mod_y', 'pitch')
SETTINGS = {'sampler': SAMPLER, 'polyphony': POLY, 'arp': ARP, 'stretching': STRETCH,
            'delay': DELAY, 'filter': FILTER, 'level_adjusts': LEVEL, 'time': TIME,
            'keyboard': KEYBOARD, 'playback': PLAYBACK, 'cut_group': CUT, 'layer': LAYER,
            'pitch': {'cents': (219, 8, 'i')}}


def unpack(data, field):
    offset, fmt, *mask = field
    if len(data) < offset + struct.calcsize('<' + fmt): return None
    value = struct.unpack_from('<' + fmt, data, offset)[0]
    if mask: return bool(value & mask[0]) if mask[0] else bool(value)
    return value if not isinstance(value, float) or math.isfinite(value) else None


def patch(data, field, value):
    offset, fmt, *mask = field
    if len(data) < offset + struct.calcsize('<' + fmt):
        raise ValueError('Field is absent in this saved format; no structure was extended')
    if mask or fmt == '?':
        if type(value) is not bool: raise ValueError('Boolean field requires true or false')
        if mask:
            current = struct.unpack_from('<' + fmt, data, offset)[0]
            value = ((current | mask[0]) if value else (current & ~mask[0])) if mask[0] else int(value)
    elif fmt in ('f', 'd'):
        if type(value) not in (int, float) or not math.isfinite(value): raise ValueError('Field requires a finite number')
    elif type(value) is not int:
        raise ValueError('Raw integer field requires an integer')
    result = bytearray(data)
    try: struct.pack_into('<' + fmt, result, offset, value)
    except (struct.error, OverflowError) as error: raise ValueError(str(error)) from None
    return bytes(result)


def metadata(project):
    from .mixing import initial_values
    values = {e.id: e.data for e in project.events}
    controls = initial_values(project)
    main_volume = controls.get(0x40000000, values[12][0] * 128 if 12 in values else None)
    result = {name: project._text(values[eid]) if eid in values else None for name, eid in TEXT.items()}
    result.update(show_info=bool(values[10][0]) if 10 in values else None,
                  song_mode=bool(values[9][0]) if 9 in values else None,
                  main_volume_raw=main_volume,
                  main_volume_source='saved_host_control' if 0x40000000 in controls else 'legacy_header' if 12 in values else None,
                  loop_active_raw=unpack(values.get(9, b''), (0, '?')),
                  pan_law_raw=unpack(values.get(23, b''), (0, 'B')),
                  pitch_cents=unpack(values.get(80, b''), (0, 'h')),
                  numerator=values[17][0] if 17 in values else None,
                  denominator=values[18][0] if 18 in values else None,
                  current_arrangement=unpack(values.get(100, b''), (0, 'H')),
                  creation_days=unpack(values.get(237, b''), (0, 'd')),
                  work_days=unpack(values.get(237, b''), (8, 'd')))
    result['work_seconds'] = result['work_days'] * 86400 if result['work_days'] is not None else None
    return result


def global_value(project, eid, data):
    from .flp import Event
    existing = next((e for e in project.events if e.id == eid), None)
    if existing: existing.data = data
    else:
        at = next((i for i, e in enumerate(project.events) if e.id in (64, 65, 99)), len(project.events))
        project.events.insert(at, Event(eid, data))


def set_metadata(project, changes):
    allowed = set(TEXT) | {'show_info', 'song_mode', 'pitch_cents', 'numerator', 'denominator', 'creation_days', 'work_seconds', 'current_arrangement',
                         'main_volume_raw', 'loop_active_raw', 'pan_law_raw'}
    if not isinstance(changes, dict) or set(changes) - allowed: raise ValueError('Unknown metadata field')
    for name, value in changes.items():
        if name in TEXT:
            if not isinstance(value, str): raise ValueError('Metadata text must be a string')
            global_value(project, TEXT[name], project._string(value))
        elif name in ('show_info', 'song_mode', 'loop_active_raw'):
            if type(value) is not bool: raise ValueError('Metadata flag must be boolean')
            if 'song_mode' in changes and 'loop_active_raw' in changes and changes['song_mode'] != changes['loop_active_raw']:
                raise ValueError('song_mode and loop_active_raw address the same native flag')
            global_value(project, {'show_info': 10, 'song_mode': 9, 'loop_active_raw': 9}[name], bytes([value]))
        elif name == 'main_volume_raw':
            from .mixing import initial_values, set_initial
            if type(value) is not int or not 0 <= value <= 16000: raise ValueError('Main volume raw must be 0..16000 (12800 = unity)')
            if 0x40000000 in initial_values(project): set_initial(project, 0x40000000, value)
            elif any(e.id == 12 for e in project.events) and value % 128 == 0:
                global_value(project, 12, bytes([value // 128]))
            else: raise ValueError('Project has no compatible main-volume control; use the live REC_MainVol operation')
        elif name == 'pan_law_raw':
            if value not in (0, 2) or type(value) is not int: raise ValueError('Pan law raw must be circular 0 or triangular 2')
            global_value(project, 23, bytes([value]))
        elif name in ('numerator', 'denominator', 'pitch_cents', 'current_arrangement'):
            if type(value) is not int: raise ValueError('Meter/pitch must be an integer')
            if name in ('numerator', 'denominator') and not 1 <= value <= 255: raise ValueError('Meter fields must be 1..255')
            eid, fmt = {'numerator': (17, 'B'), 'denominator': (18, 'B'), 'pitch_cents': (80, 'h'), 'current_arrangement': (100, 'H')}[name]
            global_value(project, eid, patch(bytes(struct.calcsize('<' + fmt)), (0, fmt), value))
        else:
            event = next((e for e in project.events if e.id == 237), None)
            if event is None: raise ValueError('Project has no work-time structure')
            if type(value) not in (int, float) or not math.isfinite(value): raise ValueError('Project time requires a finite number')
            if name == 'work_seconds' and value < 0: raise ValueError('Work time cannot be negative')
            event.data = patch(event.data, (0 if name == 'creation_days' else 8, 'd'), value if name == 'creation_days' else value / 86400)


def channel_settings(project, channel):
    spans = project.channel_spans()
    if type(channel) is not int or not 0 <= channel < len(spans): raise ValueError('Channel index is absent')
    a, b = spans[channel]; block = project.events[a:b]; events = {e.id: e for e in block}
    result = {'channel': channel, 'type': events[21].data[0]}
    if result['type'] == 5:
        result['automation_range_raw'] = [unpack(events[219].data, (offset, 'i')) for offset in (0, 4)] if 219 in events else None
        return result
    for name, fields in SETTINGS.items():
        if name == 'sampler' and result['type'] not in (0, 4) or name == 'layer' and result['type'] != 3: continue
        result[name] = {key: unpack(events[eid].data, field) if eid in events else None
                        for key, (eid, *field) in fields.items()}
    env = [e for e in block if e.id == 218]
    result['envelopes'] = {name: {key: unpack(env[i].data, field) for key, field in ENV.items()}
                           for i, name in enumerate(ENVELOPES) if i < len(env)}
    tracking = [e for e in block if e.id == 228]
    result['tracking'] = {name: {key: unpack(tracking[i].data, field) for key, field in TRACKING.items()}
                          for i, name in enumerate(('volume', 'keyboard')) if i < len(tracking)}
    if result['type'] == 3:
        result['layer']['children_iids'] = [int.from_bytes(e.data, 'little') for e in block if e.id == 94]
    return result


def set_channel_settings(project, channel, changes):
    if not isinstance(changes, dict) or set(changes) - (set(SETTINGS) | {'envelopes', 'tracking'}):
        raise ValueError('Unknown channel settings section')
    spans = project.channel_spans()
    if type(channel) is not int or not 0 <= channel < len(spans): raise ValueError('Channel index is absent')
    a, b = spans[channel]; block = project.events[a:b]; events = {e.id: e for e in block}
    if events[21].data[0] == 5: raise ValueError('Automation channels do not use instrument settings')
    for name, values in changes.items():
        if name == 'envelopes':
            env = [e for e in block if e.id == 218]
            if not isinstance(values, dict) or set(values) - set(ENVELOPES): raise ValueError('Unknown envelope')
            for kind, fields in values.items():
                i = ENVELOPES.index(kind)
                if i >= len(env) or not isinstance(fields, dict) or set(fields) - set(ENV): raise ValueError('Envelope/field is absent')
                for key, value in fields.items(): env[i].data = patch(env[i].data, ENV[key], value)
        elif name == 'tracking':
            tracking = [e for e in block if e.id == 228]; labels = ('volume', 'keyboard')
            if not isinstance(values, dict) or set(values) - set(labels): raise ValueError('Unknown tracking group')
            for kind, fields in values.items():
                i = labels.index(kind)
                if i >= len(tracking) or not isinstance(fields, dict) or set(fields) - set(TRACKING): raise ValueError('Tracking field is absent')
                for key, value in fields.items(): tracking[i].data = patch(tracking[i].data, TRACKING[key], value)
        else:
            if name == 'sampler' and events[21].data[0] not in (0, 4): raise ValueError('Sampler settings require a sample channel')
            if name == 'layer' and events[21].data[0] != 3: raise ValueError('Layer flags require a Layer channel')
            if not isinstance(values, dict) or set(values) - set(SETTINGS[name]): raise ValueError('Unknown channel setting')
            for key, value in values.items():
                eid, *field = SETTINGS[name][key]
                if eid not in events: raise ValueError('Channel field event is absent')
                events[eid].data = patch(events[eid].data, field, value)


def arrangements(project):
    result, current, track = {}, 0, None
    for event in project.events:
        if event.id == 99:
            current, track = int.from_bytes(event.data, 'little'), None
            result.setdefault(current, {'index': current, 'name': None, 'tracks': []})
        elif event.id == 241:
            result.setdefault(current, {'index': current, 'name': None, 'tracks': []})['name'] = project._text(event.data)
        elif event.id == 238 and len(event.data) >= 4:
            item = result.setdefault(current, {'index': current, 'name': None, 'tracks': []})
            track = {'track': struct.unpack_from('<I', event.data)[0], 'name': None,
                     **{key: unpack(event.data, field) for key, field in TRACK.items()}}
            item['tracks'].append(track)
        elif event.id == 239 and track is not None: track['name'] = project._text(event.data)
    return list(result.values())


def set_arrangement(project, changes):
    from .flp import Event
    if not isinstance(changes, dict) or set(changes) - {'index', 'name', 'tracks'}: raise ValueError('Unknown arrangement field')
    index = changes.get('index', 0); current = 0; track = None; active = False
    for i, event in enumerate(project.events):
        if event.id == 99:
            current = int.from_bytes(event.data, 'little')
            if current == index:
                active = True
                if 'name' in changes:
                    if i + 1 < len(project.events) and project.events[i + 1].id == 241:
                        project.events[i + 1].data = project._string(changes['name'])
                    else: project.events.insert(i + 1, Event(241, project._string(changes['name'])))
                break
    if not active: raise ValueError('Arrangement index is absent')
    for change in changes.get('tracks', []):
        if not isinstance(change, dict) or 'track' not in change or set(change) - (set(TRACK) | {'track', 'name'}):
            raise ValueError('Track edit requires track and supported fields')
        current = 0
        for i, event in enumerate(project.events):
            if event.id == 99: current = int.from_bytes(event.data, 'little')
            if current == index and event.id == 238 and int.from_bytes(event.data[:4], 'little') == change['track']:
                for key, value in change.items():
                    if key in TRACK: event.data = patch(event.data, TRACK[key], value)
                if 'name' in change:
                    if i + 1 < len(project.events) and project.events[i + 1].id == 239:
                        project.events[i + 1].data = project._string(change['name'])
                    else: project.events.insert(i + 1, Event(239, project._string(change['name'])))
                break
        else: raise ValueError('Playlist track descriptor is absent')


def pattern_controllers(project):
    result, current = {}, None
    for event in project.events:
        if event.id == 65:
            current = int.from_bytes(event.data, 'little'); result.setdefault(current, [])
        elif event.id in (64, 99, 225, 236): current = None
        elif event.id == 223 and current is not None:
            if len(event.data) % 12: raise ValueError('Unsupported pattern controller record size')
            result[current].extend({'position_raw': p, 'target_address': target, 'value_raw': value}
                                   for p, target, value in struct.iter_unpack('<III', event.data))
    return [{'pattern_number': n, 'records': r} for n, r in result.items() if r]


def set_controllers(project, spec):
    from .flp import Event
    if not isinstance(spec, dict) or set(spec) - {'pattern_number', 'records', 'mode'} or not {'pattern_number', 'records'} <= set(spec):
        raise ValueError('Controller edit requires pattern_number, records and optional mode')
    number, records, mode = spec['pattern_number'], spec['records'], spec.get('mode', 'replace')
    if mode not in ('append', 'replace') or not isinstance(records, list): raise ValueError('Choose append or replace with a records array')
    encoded = []
    for item in records:
        if not isinstance(item, dict) or set(item) != {'position_raw', 'target_address', 'value_raw'}:
            raise ValueError('Controller records require full position_raw, target_address and value_raw words')
        if any(type(v) is not int for v in item.values()) or not -0x80000000 <= item['value_raw'] <= 0xffffffff:
            raise ValueError('Controller fields require 32-bit integers')
        try: encoded.append(struct.pack('<III', item['position_raw'], item['target_address'], item['value_raw'] & 0xffffffff))
        except struct.error as error: raise ValueError(str(error)) from None
    data = b''.join(encoded)
    current, location, existing = None, None, []
    for i, event in enumerate(project.events):
        if event.id == 65:
            current = int.from_bytes(event.data, 'little')
            if current == number: location = i + 1
        elif event.id in (64, 99, 225, 236): current = None
        elif event.id == 223 and current == number: existing.append((i, event))
    if location is None: raise ValueError('Pattern is absent; create/name it before adding controllers')
    if mode == 'append': data = b''.join(e.data for _, e in existing) + data
    if existing:
        existing[0][1].data = data
        for i, _ in reversed(existing[1:]): del project.events[i]
    elif data: project.events.insert(location, Event(223, data))


def register(group, emit, json_option):
    import click
    from pathlib import Path
    from .flp import Project
    from .contracts import Result

    def reader(name, function):
        @group.command(name)
        @click.option('--input', 'source', required=True, type=click.Path(path_type=Path))
        @json_option
        def read(source):
            data = function(Project.read(source))
            emit(Result(command='project ' + name, status='verified', verified_scopes=['saved_fields'],
                        data=data if isinstance(data, dict) else {'items': data}))
    reader('metadata', metadata)
    reader('arrangements', arrangements)
    reader('controllers', pattern_controllers)

    @group.command('channel-settings')
    @click.option('--input', 'source', required=True, type=click.Path(path_type=Path))
    @click.option('--channel', required=True, type=click.IntRange(0, 4095))
    @json_option
    def settings(source, channel):
        emit(Result(command='project channel-settings', status='verified', verified_scopes=['saved_channel_fields'],
                    data=channel_settings(Project.read(source), channel)))
