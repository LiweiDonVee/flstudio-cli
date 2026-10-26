"""FL project event editing. Unknown events and untouched note bytes are retained.

This is an independent event reader for the installed FL 26 profile, not a
general serializer for every historical FL file. All writes go to a new path.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import math
import struct

from .contracts import NoteInput

NOTE = struct.Struct('<IHHIHH8B')
HEADER = struct.Struct('<4sIhHH4sI')


def text(data: bytes) -> str:
    return data.decode('utf-16le').rstrip('\0')


def string(value: str) -> bytes:
    return (value + '\0').encode('utf-16le')


def preset_events(path: Path | str) -> list[Event]:
    preset = Project.read(path)
    legacy = int(preset.version.split('.')[0]) < 11
    result = []
    for event in preset.events:
        if event.id in (201, 203, 212, 213, 155, 128):
            data = event.data
            if legacy and event.id in (201, 203):
                data = string(data.rstrip(b'\0').decode('cp1252'))
            result.append(Event(event.id, data))
    if not any(e.id == 201 for e in result) or not any(e.id == 213 for e in result):
        raise ValueError('Preset does not contain a complete generator/effect plugin state')
    return result


@dataclass
class Event:
    id: int
    data: bytes

    def encode(self) -> bytes:
        prefix = bytes([self.id])
        if self.id >= 192:
            n = len(self.data)
            while n > 127:
                prefix += bytes([(n & 127) | 128])
                n >>= 7
            prefix += bytes([n])
        return prefix + self.data


class Project:
    def __init__(self, blob: bytes, path: Path | None = None):
        self.path = path
        self.source = blob
        if len(blob) < HEADER.size:
            raise ValueError('Truncated FLP header')
        magic, size, self.format, self.channel_count, self.ppq, data_magic, length = HEADER.unpack_from(blob)
        if magic != b'FLhd' or size != 6 or data_magic != b'FLdt' or length != len(blob) - 22:
            raise ValueError('Invalid FLhd/FLdt envelope')
        self.events: list[Event] = []
        pos = 22
        self.version = 'unknown'
        while pos < len(blob):
            eid = blob[pos]
            pos += 1
            if eid < 192:
                size = 1 if eid < 64 else 2 if eid < 128 else 4
                # FL26 changed this otherwise undocumented event from four to three bytes.
                if eid == 172 and self.version.startswith('26.'):
                    size = 3
            else:
                size = 0
                for shift in range(0, 35, 7):
                    if pos >= len(blob):
                        raise ValueError('Truncated FLP variable length')
                    byte = blob[pos]
                    pos += 1
                    size |= (byte & 127) << shift
                    if not byte & 128:
                        break
                else:
                    raise ValueError('Invalid FLP variable length')
            if pos + size > len(blob):
                raise ValueError(f'Truncated FLP event {eid}')
            data = blob[pos:pos + size]
            pos += size
            if eid == 199:
                self.version = data.rstrip(b'\0').decode('ascii')
            self.events.append(Event(eid, data))

    @classmethod
    def read(cls, path: Path | str) -> Project:
        path = Path(path).resolve()
        return cls(path.read_bytes(), path)

    def encode(self) -> bytes:
        payload = b''.join(event.encode() for event in self.events)
        return HEADER.pack(b'FLhd', 6, self.format, self.channel_count, self.ppq, b'FLdt', len(payload)) + payload

    def save(self, output: Path | str) -> Path:
        output = Path(output).resolve()
        if self.path == output:
            raise ValueError('Choose a distinct output path; source projects are never overwritten')
        blob = self.encode()
        # Reparse before publishing, and use an exclusive create so no song is overwritten.
        Project(blob)
        with output.open('xb') as file:
            file.write(blob)
        return output

    def channel_spans(self) -> list[tuple[int, int]]:
        spans = []
        start = None
        for index, event in enumerate(self.events):
            if event.id == 64:
                if start is not None:
                    spans.append((start, index))
                start = index
            elif start is not None and event.id in (65, 99):
                spans.append((start, index))
                start = None
        if start is not None:
            raise ValueError('Unsupported channel section without a closing pattern/arrangement boundary')
        return spans

    def channels(self) -> list[dict]:
        result = []
        for index, (start, end) in enumerate(self.channel_spans()):
            events = self.events[start:end]
            values = {e.id: e.data for e in events}
            iid = int.from_bytes(values[64], 'little')
            levels = values.get(219)
            result.append({
                'index': index, 'iid': iid, 'name': text(values.get(203, values.get(192, b'\0\0'))),
                'type': values.get(21, b'\0')[0], 'plugin': text(values.get(201, b'\0\0')) or 'Sampler',
                'sample_path': text(values[196]) if 196 in values else None,
                'mixer_track': int.from_bytes(values.get(22, b'\0'), 'little'),
                'volume_raw': struct.unpack_from('<I', levels, 4)[0] if levels and len(levels) >= 8 else None,
                'pan_raw': struct.unpack_from('<i', levels)[0] if levels and len(levels) >= 4 else None,
                'plugin_state_sha256': hashlib.sha256(values[213]).hexdigest() if 213 in values else None,
            })
        if len(result) != self.channel_count:
            raise ValueError('FLP channel count disagrees with the event section')
        return result

    def patterns(self) -> dict[int, dict]:
        patterns = {}
        current = None
        iid_to_index = {c['iid']: c['index'] for c in self.channels()}
        for index, event in enumerate(self.events):
            if event.id == 65:
                current = int.from_bytes(event.data, 'little')
                patterns.setdefault(current, {'number': current, 'name': f'Pattern {current}', 'notes': []})
            elif current is not None and event.id == 193:
                patterns[current]['name'] = text(event.data)
            elif current is not None and event.id == 224:
                if len(event.data) % NOTE.size:
                    raise ValueError(f'Unsupported note record size in pattern {current}')
                for record in NOTE.iter_unpack(event.data):
                    pos, flags, iid, length, key, group, fine, reserved, release, midi, pan, velocity, modx, mody = record
                    patterns[current]['notes'].append({
                        'channel_index': iid_to_index.get(iid), 'channel_iid': iid,
                        'key': key, 'start_tick': pos, 'length_tick': length, 'velocity': velocity,
                        'flags': flags, 'group': group, 'fine_pitch': fine, 'release': release,
                        'midi_channel': midi, 'pan': pan, 'mod_x': modx, 'mod_y': mody,
                    })
            elif event.id in (64, 99):
                current = None
        return patterns

    def playlist_record_size(self) -> int:
        parts = tuple(int(x) for x in self.version.split('.')[:2])
        if parts >= (21, 2):
            return 80
        return 60 if parts >= (21, 0) else 32

    def playlist(self) -> list[dict]:
        result = []
        arrangement = None
        size = self.playlist_record_size()
        for event in self.events:
            if event.id == 99:
                arrangement = int.from_bytes(event.data, 'little')
            if event.id != 233:
                continue
            if len(event.data) % size:
                raise ValueError('Edited/variable-length Playlist records require another backend')
            for offset in range(0, len(event.data), size):
                record = event.data[offset:offset + size]
                pos, base, item, length, reverse, group, tag, flags = struct.unpack_from('<IHHIHHHH', record)
                if base != 20480 or reverse > 499:
                    raise ValueError('Unsupported Playlist record profile')
                result.append({'arrangement': arrangement, 'track': 500 - reverse,
                               'pattern_number': item - base if item >= base else None,
                               'channel_iid': item if item < base else None,
                               'start_tick': pos, 'length_tick': length, 'flags': flags,
                               'record_bytes': size})
        return result

    @property
    def tempo(self) -> float:
        return int.from_bytes(next(e.data for e in self.events if e.id == 156), 'little') / 1000

    def inspect(self, include_notes=True) -> dict:
        patterns = list(self.patterns().values())
        for pattern in patterns:
            pattern['note_count'] = len(pattern['notes'])
            if not include_notes:
                pattern.pop('notes')
        return {'path': str(self.path) if self.path else None, 'producer_version': self.version,
                'ppq': self.ppq, 'tempo_bpm': self.tempo, 'channels': self.channels(),
                'patterns': patterns, 'playlist': self.playlist(), 'mixer': self.mixer(),
                'event_count': len(self.events), 'source_sha256': hashlib.sha256(self.source).hexdigest()}

    def _replace_value(self, eid, data):
        for event in self.events:
            if event.id == eid:
                event.data = data
                return
        raise ValueError(f'Required FLP event {eid} not present')

    def set_tempo(self, bpm):
        if isinstance(bpm, bool) or not isinstance(bpm, (int, float)) or not math.isfinite(bpm) or not 10 <= bpm <= 522:
            raise ValueError('Tempo must be finite, 10..522 BPM')
        self._replace_value(156, struct.pack('<I', round(bpm * 1000)))

    def replace_notes(self, pattern: int, channel_index: int, notes: list[dict], append=False):
        if type(pattern) is not int or not 1 <= pattern <= 999:
            raise ValueError('Pattern number must be 1..999')
        channels = self.channels()
        if type(channel_index) is not int or not 0 <= channel_index < len(channels):
            raise ValueError('Channel index is not in this saved project')
        iid = channels[channel_index]['iid']
        validated = [NoteInput.model_validate(n) for n in notes]
        additions = b''.join(NOTE.pack(n.start_tick, 0x4000, iid, n.length_tick, n.key, 0,
                                       120, 0, 64, 0, 64, n.velocity, 128, 128) for n in validated)
        current = None
        for event in self.events:
            if event.id == 65:
                current = int.from_bytes(event.data, 'little')
            elif event.id in (64, 99):
                current = None
            elif current == pattern and event.id == 224:
                if len(event.data) % NOTE.size:
                    raise ValueError('Unsupported note record length')
                kept = b''.join(event.data[i:i + NOTE.size] for i in range(0, len(event.data), NOTE.size)
                                if append or struct.unpack_from('<H', event.data, i + 6)[0] != iid)
                event.data = kept + additions
                return
        # Score blocks precede Channel Rack data. Metadata is a separate later section.
        start = self.channel_spans()[0][0]
        self.events[start:start] = [Event(65, struct.pack('<H', pattern)), Event(224, additions)]

    def name_pattern(self, number: int, name: str):
        current = None
        for event in self.events:
            if event.id == 65:
                current = int.from_bytes(event.data, 'little')
            elif event.id in (64, 99):
                current = None
            elif current == number and event.id == 193:
                event.data = string(name)
                return
        where = next(i for i, e in enumerate(self.events) if e.id == 99)
        self.events[where:where] = [Event(65, struct.pack('<H', number)), Event(193, string(name))]

    def set_playlist(self, clips: list[dict]):
        size = self.playlist_record_size()
        records = []
        patterns = self.patterns()
        for uid, clip in enumerate(clips, 1):
            pat, track, pos, length = (clip[k] for k in ('pattern_number', 'track', 'start_tick', 'length_tick'))
            if any(type(x) is not int for x in (pat, track, pos, length)) or pat not in patterns or not 1 <= track <= 500 or pos < 0 or length <= 0:
                raise ValueError('Playlist clip must reference an existing pattern and valid track/ticks')
            record = struct.pack('<IHHIHHHH4sII', pos, 20480, 20480 + pat, length, 500 - track,
                                 0, 120, 64, bytes([64, 100, 128, 128]), 0xffffffff, 0xffffffff)
            if size == 80:
                record += struct.pack('<I', uid) + bytes(28) + struct.pack('<d', 1.0) + bytes(8)
            elif size == 60:
                record += struct.pack('<I', uid) + bytes(24)
            records.append(record)
        self._replace_value(233, b''.join(records))

    def set_channel(self, index: int, changes: dict):
        spans = self.channel_spans()
        if type(index) is not int or not 0 <= index < len(spans):
            raise ValueError('Channel index is not in this saved project')
        start, end = spans[index]
        mapping = {e.id: e for e in self.events[start:end]}
        for key, value in changes.items():
            if key == 'name':
                mapping[203].data = string(value)
            elif key == 'muted':
                if type(value) is not bool:
                    raise ValueError('muted must be a boolean')
                mapping[0].data = bytes([not value])
            elif key == 'sample_path':
                sample = Path(value).resolve()
                if not sample.is_file():
                    raise ValueError(f'Sample does not exist: {sample}')
                mapping[196].data = string(str(sample))
            elif key == 'mixer_track':
                if type(value) is not int or not 0 <= value <= 125:
                    raise ValueError('Mixer route must be 0..125')
                if 22 in mapping:
                    mapping[22].data = bytes([value])
                else:
                    self.events.insert(end, Event(22, bytes([value])))
            elif key in ('volume_raw', 'pan_raw'):
                low, high = (0, 12800) if key == 'volume_raw' else (-6400, 6400)
                if type(value) is not int or not low <= value <= high:
                    raise ValueError(f'{key} must be {low}..{high}')
                raw = bytearray(mapping[219].data)
                struct.pack_into('<I' if key == 'volume_raw' else '<i', raw, 4 if key == 'volume_raw' else 0, value)
                mapping[219].data = bytes(raw)
            elif key == 'plugin_preset':
                preset = preset_events(value)
                keep = [e for e in self.events[start:end] if e.id not in (201, 212, 213, 196)]
                for e in keep:
                    if e.id == 21:
                        e.data = b'\x02'
                location = next(i for i, e in enumerate(keep) if e.id == 21) + 1
                keep[location:location] = [e for e in preset if e.id in (201, 212, 213)]
                self.events[start:end] = keep
            else:
                raise ValueError(f'Unsupported channel change: {key}')

    def mixer_spans(self):
        start = next((i + 1 for i, event in enumerate(self.events) if event.id == 100), len(self.events))
        spans = []
        for index in range(start, len(self.events)):
            if self.events[index].id == 147:
                spans.append((start, index + 1))
                start = index + 1
        # FL writes the special Current insert before Master. UI/API order is
        # Master, ordinary inserts, Current; parameter records use that order.
        return spans[1:] + spans[:1] if spans else []

    def mixer(self) -> list[dict]:
        tracks = []
        spans = self.mixer_spans()
        for start, end in spans:
            block = self.events[start:end]
            data = {e.id: e.data for e in block}
            plugins, plugin = [], None
            for e in block:
                if e.id == 201:
                    plugin = {'name': text(e.data), 'slot': None, 'state_sha256': None}
                    plugins.append(plugin)
                elif plugin is not None and e.id == 213:
                    plugin['state_sha256'] = hashlib.sha256(e.data).hexdigest()
                elif plugin is not None and e.id == 98:
                    plugin['slot'] = int.from_bytes(e.data, 'little')
                    plugin = None
            default_name = 'Master' if not tracks else 'Current' if len(tracks) == len(spans) - 1 else f'Insert {len(tracks)}'
            tracks.append({'index': len(tracks), 'name': text(data[204]) if 204 in data else default_name,
                           'plugins': plugins, 'routes': [i for i, value in enumerate(data.get(235, b'')) if value]})
        selectors = self._mixer_selectors()
        for event in self.events:
            if event.id != 225:
                continue
            if len(event.data) % 12:
                raise ValueError('Unsupported mixer parameter record size')
            for offset in range(0, len(event.data), 12):
                ident = event.data[offset + 4]
                route = struct.unpack_from('<H', event.data, offset + 6)[0]
                track, value = selectors.get(route & 0xffc0), struct.unpack_from('<i', event.data, offset + 8)[0]
                if track is not None and track < len(tracks) and ident in (192, 193):
                    tracks[track]['volume_raw' if ident == 192 else 'pan_raw'] = value
        return tracks

    def _mixer_selectors(self):
        # Mixer REC addresses contain a host-specific prefix. Do not truncate
        # them to the old 7-bit PyFLP mask: FL's expanded mixer would alias them.
        values = []
        for event in self.events:
            if event.id == 225:
                for offset in range(0, len(event.data), 12):
                    if event.data[offset + 4] == 192:
                        values.append(struct.unpack_from('<H', event.data, offset + 6)[0] & 0xffc0)
        if len(values) != len(set(values)):
            raise ValueError('Ambiguous mixer parameter address list')
        return {selector: index for index, selector in enumerate(values)}

    def set_mixer(self, track: int, changes: dict):
        if type(track) is not int or not 0 <= track < len(self.mixer()):
            raise ValueError('Mixer index is not in this saved project')
        selectors = self._mixer_selectors()
        for key, value in changes.items():
            if key in ('name', 'muted', 'routes'):
                start, end = self.mixer_spans()[track]
                block = {e.id: e for e in self.events[start:end]}
                if key == 'name':
                    if 204 in block:
                        block[204].data = string(value)
                    else:
                        self.events.insert(start, Event(204, string(value)))
                elif key == 'muted':
                    if type(value) is not bool:
                        raise ValueError('muted must be a boolean')
                    data = bytearray(block[236].data)
                    flags = struct.unpack_from('<I', data, 4)[0]
                    struct.pack_into('<I', data, 4, flags & ~8 if value else flags | 8)
                    block[236].data = bytes(data)
                else:
                    if not isinstance(value, list) or any(type(x) is not int or not 0 <= x < len(self.mixer()) - 1 or x == track for x in value):
                        raise ValueError('routes must contain other ordinary mixer indices')
                    data = bytes(int(i in value) for i in range(max([0, *value]) + 1))
                    if 235 in block:
                        block[235].data = data
                    else:
                        self.events.insert(end - 1, Event(235, data))
                    selector = next(address for address, index in selectors.items() if index == track)
                    params = next(e for e in self.events if e.id == 225)
                    for destination in value:
                        ident = 64 + destination
                        found = False
                        records = bytearray(params.data)
                        for offset in range(0, len(records), 12):
                            addr = struct.unpack_from('<H', records, offset + 6)[0]
                            if addr == selector and records[offset + 4] == ident:
                                struct.pack_into('<i', records, offset + 8, 12800)
                                found = True
                        if not found:
                            records += struct.pack('<4sBBHi', bytes(4), ident, 31, selector, 12800)
                        params.data = bytes(records)
                continue
            if key not in ('volume_raw', 'pan_raw'):
                raise ValueError(f'Unsupported mixer change: {key}')
            low, high = (0, 16000) if key == 'volume_raw' else (-6400, 6400)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{key} must be {low}..{high}')
            found = False
            for event in self.events:
                if event.id != 225:
                    continue
                data = bytearray(event.data)
                for offset in range(0, len(data), 12):
                    encoded = struct.unpack_from('<H', data, offset + 6)[0]
                    if selectors.get(encoded & 0xffc0) == track and data[offset + 4] == (192 if key == 'volume_raw' else 193):
                        struct.pack_into('<i', data, offset + 8, value)
                        found = True
                event.data = bytes(data)
            if not found:
                raise ValueError('Mixer parameter is absent; refusing to invent a host event')

    def load_effect(self, track: int, slot: int, preset: Path | str):
        if type(slot) is not int or not 0 <= slot < 10:
            raise ValueError('Effect slot must be 0..9')
        spans = self.mixer_spans()
        if type(track) is not int or not 0 <= track < len(spans) - 1:
            raise ValueError('Mixer track is absent')
        start, end = spans[track]
        position = start
        for i in range(start, end):
            event = self.events[i]
            if event.id == 98:
                if int.from_bytes(event.data, 'little') == slot:
                    existing = self.events[position:i]
                    keep = [e for e in existing if e.id not in (201, 203, 212, 213, 155, 128)]
                    self.events[position:i] = keep + preset_events(preset)
                    return
                position = i + 1
        raise ValueError('Effect slot was not found in the mixer profile')


def create_project(spec: dict, template: Path) -> Project:
    """Create a Sampler project from a real installed empty/basic template."""
    project = Project.read(template)
    spans = project.channel_spans()
    source = next((project.events[a:b] for a, b in spans
                   if any(e.id == 196 for e in project.events[a:b])), None)
    if not source:
        raise ValueError('Template must contain a Sampler channel')
    channels = spec['channels']
    if not 1 <= len(channels) <= 128:
        raise ValueError('A project needs 1..128 sample channels')
    if project.patterns() or project.playlist():
        raise ValueError('Build template must be empty; use edit for existing projects')
    replacement = []
    for iid, channel in enumerate(channels):
        sample = Path(channel['sample_path']).resolve() if channel.get('sample_path') else None
        if sample and not sample.is_file():
            raise ValueError(f'Sample does not exist: {sample}')
        for event in source:
            data = event.data
            if event.id == 64:
                data = struct.pack('<H', iid)
            elif event.id == 203:
                data = string(channel['name'])
            elif event.id == 196:
                data = string(str(sample)) if sample else string('')
            replacement.append(Event(event.id, data))
    project.events[spans[0][0]:spans[-1][1]] = replacement
    project.channel_count = len(channels)
    project.set_tempo(spec.get('tempo_bpm', 130))
    for index, channel in enumerate(channels):
        project.set_channel(index, {k: channel[k] for k in ('mixer_track', 'volume_raw', 'pan_raw') if k in channel})
        if channel.get('plugin_preset'):
            project.set_channel(index, {'plugin_preset': channel['plugin_preset']})
    for pattern in spec['patterns']:
        number = pattern['number']
        for score in pattern['scores']:
            project.replace_notes(number, score['channel_index'], score['notes'])
        project.name_pattern(number, pattern.get('name', f'Pattern {number}'))
    project.set_playlist(spec['playlist'])
    return project
