"""Playlist surgery: detect record boundaries and preserve each opaque tail."""
from __future__ import annotations

import math
import struct


def split_records(blob: bytes) -> list[bytes]:
    if not blob:
        return []
    def head(at):
        return (at + 32 <= len(blob) and struct.unpack_from('<H', blob, at + 4)[0] == 20480
                and struct.unpack_from('<H', blob, at + 12)[0] < 500
                and struct.unpack_from('<I', blob, at + 8)[0] > 0)
    if not head(0):
        raise ValueError('Playlist has no valid initial clip signature')
    # Solve the complete segmentation: a concatenation such as 80+100+120
    # must never be mistaken for one opaque 300-byte record.
    sizes = (32, 60, 80, 88, 100, 108, 120, 128)
    starts, found = set(), blob.find(b'\x00\x50', 4)
    while found >= 0:
        at = found - 4
        if at % 4 == 0 and head(at):
            starts.add(at)
        found = blob.find(b'\x00\x50', found + 1)
    uniform = next((size for size in sizes if len(blob) % size == 0 and
                    all(at in starts for at in range(0, len(blob), size))), None)
    if uniform is not None and len(starts) == len(blob) // uniform:
        return [blob[at:at + uniform] for at in range(0, len(blob), uniform)]
    paths = {len(blob): (0, None, False)}
    for at in sorted(starts, reverse=True):
        best = None
        for size in sizes:
            suffix = paths.get(at + size)
            if suffix is None:
                continue
            count = suffix[0] + 1
            if best is None or count > best[0]:
                best = (count, at + size, suffix[2])
            elif count == best[0]:
                best = (count, best[1], True)
        if best is not None:
            paths[at] = best
    solution = paths.get(0)
    if uniform is not None and solution is not None and solution[0] == len(blob) // uniform:
        return [blob[at:at + uniform] for at in range(0, len(blob), uniform)]
    if solution is not None and solution[2]:
        raise ValueError('Playlist record boundaries are ambiguous; source is unchanged')
    if solution is not None:
        result, at = [], 0
        while at < len(blob):
            following = paths[at][1]
            result.append(blob[at:following]); at = following
        return result
    # An unfamiliar uniform tail is still detectable from repeated semantic
    # heads. One unknown-size blob without another anchor is not enough proof.
    ordered = sorted(starts)
    if len(ordered) > 1:
        stride = ordered[1]
        if stride >= 32 and ordered == list(range(0, len(blob), stride)) and len(blob) % stride == 0:
            return [blob[at:at + stride] for at in ordered]
    raise ValueError('Playlist record boundaries are incomplete; source is unchanged')


def playlist_events(project):
    arrangement = 0
    for event in project.events:
        if event.id == 99:
            arrangement = int.from_bytes(event.data, 'little')
        elif event.id == 233:
            yield arrangement, event


def record_kind(record, channels):
    base, item = struct.unpack_from('<HH', record, 4)
    if item >= base:
        return 'pattern'
    channel = channels.get(item)
    return {4: 'audio', 5: 'automation'}.get(channel['type'], 'channel') if channel else 'channel'


def source_window(record, kind):
    if kind not in ('pattern', 'automation', 'audio'):
        return {'units': 'opaque', 'raw_hex': record[24:32].hex()}
    if kind == 'pattern':
        begin, end = struct.unpack_from('<II', record, 24)
        return {'units': 'ticks', 'start': begin if begin != 0xffffffff else None,
                'end': end if end != 0xffffffff else None}
    begin, end = struct.unpack_from('<ff', record, 24)
    return {'units': 'milliseconds' if kind == 'audio' else 'beats',
            'start': begin if math.isfinite(begin) and begin >= 0 else None,
            'end': end if math.isfinite(end) and end >= 0 else None}


def set_window(data, kind, start_tick, length_tick, project):
    if not 0 <= start_tick <= 0xffffffff - length_tick:
        raise ValueError('Source window exceeds the FL tick range')
    if kind == 'pattern':
        struct.pack_into('<II', data, 24, start_tick, start_tick + length_tick)
    elif kind == 'automation':
        struct.pack_into('<ff', data, 24, start_tick / project.ppq, (start_tick + length_tick) / project.ppq)
    elif kind == 'audio':
        scale = 60000 / (project.tempo * project.ppq)
        struct.pack_into('<ff', data, 24, start_tick * scale, (start_tick + length_tick) * scale)


def initialize_window(project, data, clip, kind):
    set_window(data, kind, clip.get('source_start_tick') or 0, clip['length_tick'], project)
    start, end = clip.get('source_start_ms'), clip.get('source_end_ms')
    if start is not None or end is not None:
        if (kind != 'audio' or start is None or end is None or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or not 0 <= start < end):
            raise ValueError('Audio cuts require finite 0 <= source_start_ms < source_end_ms')
        struct.pack_into('<ff', data, 24, start, end)
    if clip.get('gain') is not None:
        gain = clip['gain']
        if kind != 'audio' or len(data) < 80 or type(gain) not in (int, float) or not math.isfinite(gain) or gain < 0:
            raise ValueError('Gain requires a nonnegative finite value and an extended Audio Clip')
        struct.pack_into('<f', data, 52, gain)


def read_playlist(project):
    result, indices = [], {}
    channels = {c['iid']: c for c in project.channels()}
    for arrangement, event in playlist_events(project):
        for record in split_records(event.data):
            pos, base, item, length, reverse, group = struct.unpack_from('<IHHIHH', record)
            index = indices.get(arrangement, 0)
            indices[arrangement] = index + 1
            flags = struct.unpack_from('<H', record, 18)[0]
            channel = channels.get(item) if item < base else None
            kind = record_kind(record, channels)
            gain = struct.unpack_from('<f', record, 52)[0] if kind == 'audio' and len(record) >= 80 else None
            if gain is not None and not math.isfinite(gain): gain = None
            result.append({'arrangement': arrangement, 'clip_index': index, 'track': 500 - reverse,
                           'instance_id': struct.unpack_from('<I', record, 32)[0] if len(record) >= 60 else None,
                           'kind': kind, 'source_window': source_window(record, kind),
                           'gain': gain,
                           'pattern_number': item - base if item >= base else None,
                           'channel_iid': item if item < base else None,
                           'channel_index': channel['index'] if channel else None,
                           'start_tick': pos, 'length_tick': length, 'group': group,
                           'flags': flags, 'muted': bool(flags & 0x2000), 'record_bytes': len(record),
                           'opaque_tail_hex': record[32:].hex()})
    return result


def patch_playlist(project, edits):
    if not isinstance(edits, list):
        raise ValueError('playlist_edits must be an array')
    if not edits:
        return
    channels = {ch['iid']: ch for ch in project.channels()}
    by_arrangement = {}
    for arrangement, event in playlist_events(project):
        if arrangement in by_arrangement:
            raise ValueError('Multiple playlist blobs in one arrangement need an explicit format profile')
        by_arrangement[arrangement] = (event, split_records(event.data))
    seen = set()
    for edit in edits:
        allowed = {'arrangement', 'clip_index', 'start_tick', 'length_tick', 'track', 'group', 'muted',
                   'source_start_tick', 'source_start_ms', 'source_end_ms', 'gain', 'delete', 'duplicate'}
        if not isinstance(edit, dict) or set(edit) - allowed or 'clip_index' not in edit:
            raise ValueError('Playlist edit requires clip_index and supported head fields')
        arrangement, index = edit.get('arrangement', 0), edit['clip_index']
        if type(arrangement) is not int or arrangement not in by_arrangement:
            raise ValueError('Playlist arrangement is absent')
        event, records = by_arrangement[arrangement]
        if type(index) is not int or not 0 <= index < len(records) or (arrangement, index) in seen:
            raise ValueError('Each clip_index must identify one original record once')
        seen.add((arrangement, index))
        record = records[index]
        data = bytearray(record)
        kind = record_kind(record, channels)
        for field, offset, fmt, low, high in (
            ('start_tick', 0, '<I', 0, 0xffffffff), ('length_tick', 8, '<I', 1, 0xffffffff),
            ('track', 12, '<H', 1, 500), ('group', 14, '<H', 0, 65535)):
            if field in edit:
                value = edit[field]
                if type(value) is not int or not low <= value <= high:
                    raise ValueError(f'{field} must be an integer {low}..{high}')
                struct.pack_into(fmt, data, offset, 500 - value if field == 'track' else value)
        if 'muted' in edit:
            if type(edit['muted']) is not bool:
                raise ValueError('muted must be boolean')
            flags = struct.unpack_from('<H', data, 18)[0]
            struct.pack_into('<H', data, 18, flags | 0x2000 if edit['muted'] else flags & ~0x2000)
        if 'source_start_tick' in edit:
            start = edit['source_start_tick']
            if type(start) is not int or not 0 <= start < 0xffffffff:
                raise ValueError('source_start_tick must be a nonnegative integer')
            if kind not in ('pattern', 'automation'):
                raise ValueError('Audio source windows use source_start_ms and source_end_ms')
            length = struct.unpack_from('<I', data, 8)[0]
            set_window(data, kind, start, length, project)
        elif 'length_tick' in edit and kind in ('pattern', 'automation'):
            window = source_window(record, kind)
            start = window['start'] or 0
            if kind == 'automation': start = round(start * project.ppq)
            set_window(data, kind, start, edit['length_tick'], project)
        milliseconds = {'source_start_ms', 'source_end_ms'} & set(edit)
        if milliseconds or ('length_tick' in edit and kind == 'audio'):
            if kind != 'audio' or (milliseconds and len(milliseconds) != 2):
                raise ValueError('Audio cuts require both source_start_ms and source_end_ms')
            window = source_window(record, kind)
            old_length = struct.unpack_from('<I', record, 8)[0]
            begin, end = window['start'], window['end']
            scale = ((end - begin) / old_length if begin is not None and end is not None and end > begin
                     else 60000 / (project.tempo * project.ppq))
            if milliseconds:
                begin, end = edit['source_start_ms'], edit['source_end_ms']
                if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (begin, end)) or not 0 <= begin < end):
                    raise ValueError('Audio cuts require finite 0 <= source_start_ms < source_end_ms')
                if 'length_tick' not in edit:
                    struct.pack_into('<I', data, 8, max(1, round((end - begin) / scale)))
            else:
                begin = begin or 0
                end = begin + edit['length_tick'] * scale
            struct.pack_into('<ff', data, 24, begin, end)
        if 'gain' in edit:
            gain = edit['gain']
            if kind != 'audio' or len(data) < 80 or type(gain) not in (int, float) or not math.isfinite(gain) or gain < 0:
                raise ValueError('Clip gain requires a nonnegative finite audio gain and an extended record')
            struct.pack_into('<f', data, 52, gain)
        for key in ('delete', 'duplicate'):
            if key in edit and type(edit[key]) is not bool:
                raise ValueError(f'{key} must be boolean')
        if edit.get('delete') and edit.get('duplicate'):
            raise ValueError('A clip cannot be deleted and duplicated together')
        if edit.get('duplicate'):
            # FL-authored extended records carry an instance ID at byte 32.
            if len(data) >= 60:
                next_id = max((struct.unpack_from('<I', r, 32)[0] for r in records if r and len(r) >= 60), default=0) + 1
                struct.pack_into('<I', data, 32, next_id)
            records.append(bytes(data))
        else:
            records[index] = b'' if edit.get('delete') else bytes(data)
    for event, records in by_arrangement.values():
        event.data = b''.join(sorted((r for r in records if r), key=lambda r: struct.unpack_from('<I', r)[0]))


def write_playlist(project, clips, arrangement=0):
    matches = [e for a, e in playlist_events(project) if a == arrangement]
    if len(matches) != 1:
        raise ValueError('Choose one existing arrangement playlist')
    event = matches[0]
    previous = split_records(event.data)
    if not previous:
        # Existing verified empty-project builder supplies the measured FL
        # template. Appending to an edited project always uses its own record.
        project._set_fresh_playlist(clips, event)
        return
    patterns, channels = project.patterns(), project.channels()
    channel_map = {ch['iid']: ch for ch in channels}
    templates = {}
    for old in previous:
        templates.setdefault(record_kind(old, channel_map), old)
    records = []
    next_id = max((struct.unpack_from('<I', r, 32)[0] for r in previous if len(r) >= 60), default=0) + 1
    for index, clip in enumerate(clips):
        channel, pattern = clip.get('channel_index'), clip.get('pattern_number')
        if (channel is None) == (pattern is None):
            raise ValueError('Choose pattern_number or channel_index for each clip')
        if channel is not None:
            if type(channel) is not int or not 0 <= channel < len(channels) or channels[channel]['type'] not in (4, 5):
                raise ValueError('Channel clips require an existing Audio Clip or Automation channel')
            item = channels[channel]['iid']
        else:
            if type(pattern) is not int or pattern not in patterns:
                raise ValueError('Playlist pattern is absent')
            item = 20480 + pattern
        position, length, track = (clip[k] for k in ('start_tick', 'length_tick', 'track'))
        if any(type(x) is not int for x in (position, length, track)) or position < 0 or length <= 0 or not 1 <= track <= 500:
            raise ValueError('Invalid playlist position, length or track')
        kind = 'pattern' if channel is None else 'audio' if channels[channel]['type'] == 4 else 'automation'
        if kind in templates:
            data = bytearray(templates[kind])
        else:
            from .flp import Event
            # No cross-kind tail cloning: the existing measured neutral
            # builder supplies this missing kind, using the same base layout.
            size = next((len(r) for r in previous if len(r) in (32, 60, 80, 88)), project.playlist_record_size())
            scratch = Event(233, b'')
            project._set_fresh_playlist([clip], scratch, size)
            data = bytearray(scratch.data)
        struct.pack_into('<IHHIHH', data, 0, position, 20480, item, length, 500 - track, clip.get('group', 0))
        initialize_window(project, data, clip, kind)
        if len(data) >= 60:
            struct.pack_into('<I', data, 32, next_id + index)
        records.append(bytes(data))
    event.data = b''.join(sorted(records, key=lambda r: struct.unpack_from('<I', r)[0]))


def register(app, emit, json_option):
    from pathlib import Path
    import click
    from .contracts import Result
    from .flp import Project
    from .json_output import decode_json

    @app.group('playlist')
    @json_option
    def group():
        """Inspect/patch pattern, audio and automation clips, preserving opaque tails."""

    @group.command('list')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @json_option
    def show(project):
        emit(Result(command='playlist list', status='verified', verified_scopes=['saved_playlist'],
                    data={'clips': read_playlist(Project.read(project))}))

    @group.command('edit')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def edit(project, request, output, dry_run):
        doc = Project.read(project)
        before = read_playlist(doc)
        patch_playlist(doc, decode_json(request.read_text(encoding='utf-8-sig')))
        after = read_playlist(doc)
        data = {'before': before, 'after': after, 'output': str(output.resolve()), 'live_applied': False}
        if dry_run:
            data.update(applied_count=None, file_effects=[])
            emit(Result(command='playlist edit', status='planned', data=data))
            return
        doc.save(output)
        if read_playlist(Project.read(output)) != after:
            raise ValueError('Saved playlist differs from requested clips')
        emit(Result(command='playlist edit', status='artifact_ready', verified_scopes=['saved_playlist'], data=data))
