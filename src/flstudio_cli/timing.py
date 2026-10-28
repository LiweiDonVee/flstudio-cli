"""Arrangement markers and tempo-aware musical time, without changing FL."""
from __future__ import annotations

from bisect import bisect_right
import math
import struct


def integrate(beats, bpm0, bpm1):
    if min(bpm0, bpm1) <= 0: raise ValueError('Tempo must stay positive')
    if abs(bpm1 - bpm0) < 1e-10: return beats * 60 / bpm0
    return 60 * beats * math.log(bpm1 / bpm0) / (bpm1 - bpm0)


class TempoMap:
    def __init__(self, project, end_tick, arrangement=None):
        from .automation import read_all
        from .fields import pattern_controllers
        self.reason, self.segments, self.starts, self.prefix = None, [], [], []
        self.ppq, self.default_bpm = project.ppq, project.tempo
        if arrangement is None:
            arrangement = next((int.from_bytes(e.data, 'little') for e in project.events if e.id == 100), 0)
        for group in pattern_controllers(project):
            if any(r['target_address'] == 0x40000005 for r in group['records']):
                self.reason = 'pattern_tempo_events_require_native_timing'; return
        curves = {c['channel_iid']: c for c in read_all(project) if 0x40000005 in c['target_addresses']}
        clips = sorted((c for c in project.playlist() if c['arrangement'] == arrangement and not c['muted'] and
                        c['channel_iid'] in curves), key=lambda c: c['start_tick'])
        cursor, bpm, total = 0.0, project.tempo, 0.0
        def add(a, b, left, right):
            nonlocal total
            if b <= a: return
            self.starts.append(a); self.prefix.append(total); self.segments.append((a, b, left, right))
            total += integrate(b - a, left, right)
        for clip in clips:
            curve = curves[clip['channel_iid']]; points = curve['points']
            begin, end = clip['start_tick'] / self.ppq, (clip['start_tick'] + clip['length_tick']) / self.ppq
            if begin < cursor - 1e-8:
                self.reason = 'overlapping_tempo_clips_require_native_timing'; return
            if any((p['flags'] & 0xffff) not in (0, 1, 2) or
                   ((p['flags'] & 0xffff) != 2 and abs(p['tension']) > 1e-8) for p in points[1:]):
                self.reason = 'nonlinear_tempo_curve_requires_native_timing'; return
            if not points: continue
            add(cursor, begin, bpm, bpm)
            offset = clip['source_window']['start'] or 0.0
            positions = [p['position_beats'] for p in points]
            minimum, maximum = curve['range_raw']
            def value(at):
                index = bisect_right(positions, at) - 1
                if index < 0: v = points[0]['value']
                elif index + 1 >= len(points): v = points[-1]['value']
                else:
                    a, b = points[index], points[index + 1]
                    if b['flags'] & 0xffff == 2: v = a['value']
                    else:
                        fraction = (at - a['position_beats']) / (b['position_beats'] - a['position_beats'])
                        v = a['value'] + fraction * (b['value'] - a['value'])
                return 10 + 512 * (minimum + (maximum - minimum) * v) / 12800
            cuts = sorted({begin, end} | {begin + p - offset for p in positions if offset < p < offset + end - begin})
            for a, b in zip(cuts, cuts[1:]):
                # At a duplicate point, the right-hand value starts the next
                # segment; the left-hand value ends the previous segment.
                left = value(offset + a - begin)
                right_pos = offset + b - begin
                index = bisect_right(positions, right_pos) - 1
                next_index = bisect_right(positions, offset + a - begin)
                if next_index < len(points) and points[next_index]['flags'] & 0xffff == 2:
                    right = left
                elif index >= 0 and positions[index] == right_pos:
                    while index > 0 and positions[index - 1] == right_pos: index -= 1
                    right = 10 + 512 * (minimum + (maximum - minimum) * points[index]['value']) / 12800
                else: right = value(right_pos)
                add(a, b, left, right)
            cursor, bpm = end, value(offset + end - begin)
        add(cursor, max(cursor, end_tick / self.ppq), bpm, bpm)
        self.total = total

    def seconds(self, tick):
        if self.reason: return None
        beat = tick / self.ppq
        if not self.segments: return beat * 60 / self.default_bpm
        index = bisect_right(self.starts, beat) - 1
        if index < 0: return beat * 60 / self.default_bpm
        a, b, left, right = self.segments[index]
        if beat >= b: return self.prefix[index] + integrate(b - a, left, right) + (beat - b) * 60 / right
        current = left + (right - left) * (beat - a) / (b - a)
        return self.prefix[index] + integrate(beat - a, left, current)


def marker_blocks(project):
    arrangement, pattern, current = 0, None, None
    for i, event in enumerate(project.events):
        if event.id == 148:
            if current is not None: yield current[0], i, current[1], current[2]
            current = (i, arrangement, pattern)
        elif event.id not in (205, 33, 34, 46, 45, 168, 101) and current is not None:
            yield current[0], i, current[1], current[2]; current = None
        if event.id == 99: arrangement = int.from_bytes(event.data, 'little')
        elif event.id == 65: pattern = int.from_bytes(event.data, 'little')
        elif event.id in (64, 225, 236, 233): pattern = None
    if current is not None: yield current[0], len(project.events), current[1], current[2]


def markers(project, with_seconds=True):
    result = []
    for start, end, arrangement, pattern in marker_blocks(project):
        block = project.events[start:end]; raw = int.from_bytes(block[0].data, 'little')
        values = {e.id: e.data for e in block}
        result.append({'arrangement': arrangement, 'pattern_number': pattern, 'position_tick': raw & 0xffffff,
                       'action_raw': raw >> 24, 'kind': 'signature' if raw >> 24 == 8 else 'marker' if raw >> 24 == 0 else 'special',
                       'name': project._text(values[205]) if 205 in values else '',
                       'numerator': values[33][0] if 33 in values else None,
                       'denominator': values[34][0] if 34 in values else None})
    if with_seconds:
        maps = {}
        for marker in result:
            arrangement = marker['arrangement']
            if marker['pattern_number'] is not None:
                marker.update(seconds=None, timing_reason='pattern_relative_marker'); continue
            if arrangement not in maps:
                end_tick = max((m['position_tick'] for m in result if m['arrangement'] == arrangement), default=0)
                maps[arrangement] = TempoMap(project, end_tick, arrangement)
            clock = maps[arrangement]
            marker.update(seconds=clock.seconds(marker['position_tick']), timing_reason=clock.reason)
    return result


def set_markers(project, spec):
    from .flp import Event
    from .entities import pattern_blocks
    if not isinstance(spec, dict) or set(spec) - {'arrangement', 'pattern_number', 'markers'} or not isinstance(spec.get('markers'), list):
        raise ValueError('Marker edit requires markers and an arrangement or pattern_number')
    arrangement, pattern = spec.get('arrangement', 0), spec.get('pattern_number')
    if pattern is not None and 'arrangement' in spec: raise ValueError('Choose arrangement or pattern_number')
    encoded = []
    for marker in sorted(spec['markers'], key=lambda value: value.get('position_tick', 0)):
        allowed = {'position_tick', 'name', 'kind', 'action_raw', 'numerator', 'denominator'}
        if not isinstance(marker, dict) or set(marker) - allowed: raise ValueError('Unknown marker field')
        tick = marker.get('position_tick'); kind = marker.get('kind', 'marker')
        action = marker.get('action_raw', 8 if kind == 'signature' else 0)
        if type(tick) is not int or not 0 <= tick <= 0xffffff or type(action) is not int or not 0 <= action <= 255:
            raise ValueError('Marker tick/action is out of range')
        if not isinstance(marker.get('name', ''), str): raise ValueError('Marker name requires text')
        encoded.append(Event(148, struct.pack('<I', tick | action << 24)))
        for key, eid, global_id in (('numerator', 33, 17), ('denominator', 34, 18)):
            default = next((e.data[0] for e in project.events if e.id == global_id), 4)
            value = marker.get(key, None if action == 8 else default)
            if type(value) is not int or not 1 <= value <= 255: raise ValueError('Signature markers require numerator/denominator')
            encoded.append(Event(eid, bytes([value])))
        encoded.append(Event(205, project._string(marker.get('name', ''))))
    for start, end, ar, pat in reversed(list(marker_blocks(project))):
        if (pattern is not None and pat == pattern) or (pattern is None and pat is None and ar == arrangement):
            del project.events[start:end]
    if pattern is not None:
        block = next(pattern_blocks(project, pattern), None)
        if block is None: raise ValueError('Pattern marker scope is absent')
        at = block[1]
    else:
        current, at = 0, None
        for i, event in enumerate(project.events):
            if event.id == 99: current = int.from_bytes(event.data, 'little')
            elif event.id == 233 and current == arrangement:
                at = i + 1; break
        if at is None: raise ValueError('Arrangement marker scope is absent')
    project.events[at:at] = encoded


def register(group, emit, json_option):
    import click
    from pathlib import Path
    from .flp import Project
    from .contracts import Result

    @group.command('markers')
    @click.option('--input', 'source', required=True, type=click.Path(path_type=Path))
    @json_option
    def read(source):
        emit(Result(command='project markers', status='verified', verified_scopes=['saved_markers'], data={'markers': markers(Project.read(source))}))
