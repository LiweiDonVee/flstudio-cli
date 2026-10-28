"""Patch existing automation curves without changing their link/header/trailer."""
from __future__ import annotations

import math
import struct


def locate(project, channel, spans=None):
    spans = project.channel_spans() if spans is None else spans
    if type(channel) is not int or not 0 <= channel < len(spans):
        raise ValueError('Automation channel index is absent')
    start, end = spans[channel]
    block = project.events[start:end]
    kind = next((e.data[0] for e in block if e.id == 21), None)
    if kind != 5:
        raise ValueError('Target is not an automation channel')
    event = next((e for e in block if e.id == 234), None)
    if event is None or len(event.data) < 21:
        raise ValueError('Automation point container is absent or truncated')
    count = struct.unpack_from('<I', event.data, 17)[0]
    if count > (len(event.data) - 21) // 24:
        raise ValueError('Automation point count exceeds its container')
    return event, count


def read_curve(project, channel, channel_info=None, spans=None, known_links=None):
    event, count = locate(project, channel, spans)
    position, points = 0.0, []
    for i in range(count):
        delta, value, tension, flags = struct.unpack_from('<ddfI', event.data, 21 + i * 24)
        position += delta
        if not all(math.isfinite(x) for x in (position, value, tension)):
            raise ValueError('Automation contains nonfinite point data')
        points.append({'position_beats': position, 'value': value, 'tension': tension, 'flags': flags,
                       'mode': flags & 0xffff, 'selected': bool(flags & 0xff0000)})
    iid = channel_info['iid'] if channel_info is not None else project.channels()[channel]['iid']
    links = known_links.get(iid, []) if known_links is not None else [
        struct.unpack_from('<I', e.data, 8)[0] for e in project.events
        if e.id == 227 and len(e.data) == 20 and struct.unpack_from('<I', e.data)[0] >> 16 == iid]
    block = project.events[slice(*(spans or project.channel_spans())[channel])]
    levels = next((e.data for e in block if e.id == 219), b'')
    limits = struct.unpack_from('<ii', levels) if len(levels) >= 8 else (0, 12800)
    return {'channel': channel, 'channel_iid': iid, 'points': points, 'target_addresses': links,
            'range_raw': list(limits),
            'header_hex': event.data[:17].hex(), 'trailer_hex': event.data[21 + count * 24:].hex()}


def read_all(project):
    spans = project.channel_spans()
    links = {}
    for event in project.events:
        if event.id == 227 and len(event.data) == 20:
            iid, target = struct.unpack_from('<I', event.data)[0] >> 16, struct.unpack_from('<I', event.data, 8)[0]
            links.setdefault(iid, []).append(target)
    return [read_curve(project, ch['index'], ch, spans, links) for ch in project.channels() if ch['type'] == 5]


def write_curve(project, channel, points):
    event, count = locate(project, channel)
    if not isinstance(points, list):
        raise ValueError('Automation points must be an array')
    encoded, previous = [], 0.0
    for index, point in enumerate(points):
        if not isinstance(point, dict) or set(point) - {'position_beats', 'value', 'tension', 'flags', 'curve', 'mode', 'selected'}:
            raise ValueError('Automation points accept position_beats, value, tension, curve and opaque flags')
        old_tension = struct.unpack_from('<f', event.data, 37 + index * 24)[0] if index < count else 0.0
        position, value, tension = point['position_beats'], point['value'], point.get('tension', old_tension)
        if (any(type(x) not in (float, int) or not math.isfinite(x) for x in (position, value, tension))
                or position < previous or not -.001 <= value <= 1.001 or not -1 <= tension <= 1):
            raise ValueError('Points require sorted nonnegative beats, finite value 0..1 and tension -1..1')
        # An existing point retains its exact FL interpolation bytes unless
        # explicitly changed. New points inherit the first FL-authored point.
        inherited = struct.unpack_from('<I', event.data, 41 + min(index, max(0, count - 1)) * 24)[0] if count else 0
        flags = point.get('flags', inherited)
        if type(flags) is not int or not 0 <= flags <= 0xffffffff:
            raise ValueError('Automation flags must be a uint32')
        if 'curve' in point:
            modes = {'linear': 0, 'single': 0, 'double': 1, 'hold': 2}
            if point['curve'] not in modes: raise ValueError('Named curve must be linear, single, double or hold; other FL modes use mode')
            flags = flags & 0xffff0000 | modes[point['curve']]
            if point['curve'] == 'linear': tension = 0.0
        if 'mode' in point:
            mode = point['mode']
            if type(mode) is not int or not 0 <= mode <= 65535: raise ValueError('Curve mode must be a uint16')
            flags = flags & 0xffff0000 | mode
        if 'selected' in point:
            if type(point['selected']) is not bool: raise ValueError('Point selected must be boolean')
            flags = flags & 0xff00ffff | int(point['selected']) << 16
        encoded.append(struct.pack('<ddfI', position - previous, value, tension, flags))
        previous = position
    event.data = event.data[:17] + struct.pack('<I', len(points)) + b''.join(encoded) + event.data[21 + count * 24:]


def target_address(project, target):
    """Translate an explicit saved object to its actual FL REC address."""
    from .mixing import track_address, slot_address, send_address
    if not isinstance(target, dict) or 'kind' not in target:
        raise ValueError('Automation target requires an explicit kind and object indices')
    kind = target['kind']
    if kind == 'tempo' and set(target) == {'kind'}:
        return 0x40000005
    if kind in ('channel_volume', 'channel_pan', 'channel_pitch', 'generator_param'):
        required = {'kind', 'channel', 'param'} if kind == 'generator_param' else {'kind', 'channel'}
        if set(target) != required:
            raise ValueError('Channel automation target fields do not match its kind')
        channels = project.channels()
        index = target['channel']
        if type(index) is not int or not 0 <= index < len(channels):
            raise ValueError('Automation target channel is absent')
        if kind == 'generator_param':
            param = target['param']
            if type(param) is not int or not 0 <= param < 0x8000:
                raise ValueError('Plugin parameter index must be 0..32767')
            control = 0x8000 + param
        else:
            control = {'channel_volume': 0, 'channel_pan': 1, 'channel_pitch': 4}[kind]
        return channels[index]['iid'] << 16 | control
    if kind in ('mixer_volume', 'mixer_pan', 'mixer_send', 'effect_param', 'effect_wet'):
        required = {'kind', 'track'}
        if kind == 'mixer_send': required |= {'to'}
        if kind in ('effect_param', 'effect_wet'): required |= {'slot'}
        if kind == 'effect_param': required |= {'param'}
        if set(target) != required:
            raise ValueError('Mixer automation target fields do not match its kind')
        track = target['track']
        if kind == 'mixer_send':
            destination = target['to']
            track_address(project, destination)
            if destination not in project.mixer()[track]['routes']:
                raise ValueError('Create the send route before automating its level')
            return send_address(project, track, destination)
        if kind in ('effect_param', 'effect_wet'):
            project._effect_state(track, target['slot'])
            base = slot_address(project, track, target['slot'])
            if kind == 'effect_wet': return base | 1
            param = target['param']
            if type(param) is not int or not 0 <= param < 0x8000:
                raise ValueError('Plugin parameter index must be 0..32767')
            return (base & 0xffff0000) | (0x8000 + param)
        return track_address(project, track) | (192 if kind == 'mixer_volume' else 193)
    raise ValueError('Unsupported or ambiguous automation target')


def create_curve(project, spec, template=None):
    """Clone a locally FL-authored channel AND controller link, then retarget.

    The binary link is never assembled from guessed flags/trailers. Sources are
    not redistributed; the installed FL demo supplies its authored structure.
    """
    from pathlib import Path
    from .flp import Project, Event, string
    from .timeline import playlist_events, split_records
    allowed = {'name', 'target', 'points', 'track', 'start_tick', 'length_tick', 'arrangement', 'template', 'template_channel', 'range_raw'}
    if not isinstance(spec, dict) or set(spec) - allowed or not {'name', 'target', 'points'} <= set(spec):
        raise ValueError('New automation requires name, target, points and optional placement/template fields')
    if not isinstance(spec['name'], str) or not spec['name']:
        raise ValueError('Automation name must be nonempty')
    limits = spec.get('range_raw', [0, 12800])
    if not isinstance(limits, list) or len(limits) != 2 or any(type(v) is not int or not -0x80000000 <= v <= 0x7fffffff for v in limits):
        raise ValueError('range_raw requires two signed 32-bit integers')
    address = target_address(project, spec['target'])
    source = Project.read(spec.get('template') or template or
                          Path('C:/Program Files/Image-Line/FL Studio 2026/Data/Demo projects/NewStuff.flp'))
    candidates = [ch for ch in source.channels() if ch['type'] == 5]
    chosen = next((ch for ch in candidates if spec.get('template_channel', ch['index']) == ch['index']), None)
    if chosen is None:
        raise ValueError('Choose an FL-authored automation channel as template')
    a, b = source.channel_spans()[chosen['index']]
    link = next((e.data for e in source.events if e.id == 227 and len(e.data) == 20
                 and struct.unpack_from('<I', e.data)[0] == chosen['iid'] << 16), None)
    if link is None:
        raise ValueError('Template has no supported FL-authored automation-controller link')
    if any(e.id == 227 and len(e.data) == 20 and struct.unpack_from('<I', e.data, 8)[0] == address
           for e in project.events):
        raise ValueError('Target already has a controller link; edit its existing curve instead')
    iid = max((ch['iid'] for ch in project.channels()), default=-1) + 1
    if iid >= 0x1000:
        raise ValueError('No free global channel identity remains')
    channel = len(project.channels())
    clone = [Event(e.id, e.data) for e in source.events[a:b]]
    for event in clone:
        if event.id == 64: event.data = struct.pack('<H', iid)
        elif event.id == 203: event.data = string(spec['name'])
        elif event.id == 219 and len(event.data) >= 8:
            levels = bytearray(event.data)
            struct.pack_into('<ii', levels, 0, *limits)
            event.data = bytes(levels)
    spans = project.channel_spans()
    insert_at = spans[-1][1] if spans else next((i for i, e in enumerate(project.events)
        if e.id in (65, 99, 100, 225, 233, 236, 238)), len(project.events))
    project.events[insert_at:insert_at] = clone
    project.channel_count += 1
    write_curve(project, channel, [{'flags': 0, 'tension': 0.0, **point} for point in spec['points']])
    linked = bytearray(link)
    struct.pack_into('<I', linked, 0, iid << 16)
    struct.pack_into('<I', linked, 8, address)
    project.events.insert(project.channel_spans()[0][0], Event(227, bytes(linked)))
    start_tick = spec.get('start_tick', 0)
    length_tick = spec.get('length_tick', max(1, round(max((p['position_beats'] for p in spec['points']), default=1) * project.ppq)))
    arrangement = spec.get('arrangement', 0)
    # Existing clip tails remain attached to their original records. New
    # auto-clip records use the target arrangement's own byte template.
    event = next((e for ar, e in playlist_events(project) if ar == arrangement), None)
    if event is None:
        raise ValueError('Automation placement arrangement is absent')
    existing = split_records(event.data)
    project.set_playlist([{'channel_index': channel, 'track': spec.get('track', 2),
                           'start_tick': start_tick, 'length_tick': length_tick}], arrangement)
    addition = split_records(event.data)
    event.data = b''.join(sorted(existing + addition, key=lambda r: struct.unpack_from('<I', r)[0]))
    return read_curve(project, channel)


def register(app, emit, json_option):
    from pathlib import Path
    import click
    from .contracts import Result
    from .flp import Project
    from .json_output import decode_json

    @app.group('automation')
    @json_option
    def group():
        """Read/edit FL-authored automation curves and their interpolation bytes."""

    @group.command('list')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @click.option('--channel', type=click.IntRange(0))
    @json_option
    def inspect(project, channel):
        doc = Project.read(project)
        data = read_curve(doc, channel) if channel is not None else {'curves': read_all(doc)}
        emit(Result(command='automation list', status='verified', verified_scopes=['saved_automation'], data=data))

    @group.command('create')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def create(project, request, output, dry_run):
        doc = Project.read(project)
        curve = create_curve(doc, decode_json(request.read_text(encoding='utf-8-sig')))
        data = {'curve': curve, 'output': str(output.resolve()), 'live_applied': False}
        if dry_run:
            data.update(applied_count=None, file_effects=[])
            emit(Result(command='automation create', status='planned', data=data))
            return
        doc.save(output)
        if read_curve(Project.read(output), curve['channel']) != curve:
            raise ValueError('New automation link or curve differs after saving')
        emit(Result(command='automation create', status='artifact_ready', verified_scopes=['saved_automation', 'saved_controller_link'], data=data))

    @group.command('edit')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @click.option('--channel', required=True, type=click.IntRange(0))
    @click.option('--points', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def edit(project, channel, points, output, dry_run):
        doc = Project.read(project)
        before = read_curve(doc, channel)
        write_curve(doc, channel, decode_json(points.read_text(encoding='utf-8-sig')))
        after = read_curve(doc, channel)
        data = {'before': before, 'after': after, 'output': str(output.resolve()), 'live_applied': False}
        if dry_run:
            data.update(applied_count=None, file_effects=[])
            emit(Result(command='automation edit', status='planned', data=data))
            return
        doc.save(output)
        if read_curve(Project.read(output), channel) != after:
            raise ValueError('Saved automation differs from the requested curve')
        emit(Result(command='automation edit', status='artifact_ready', verified_scopes=['saved_automation'], data=data))
