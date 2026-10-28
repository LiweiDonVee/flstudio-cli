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

NOTE = struct.Struct('<IHHIHH8B')
HEADER = struct.Struct('<4sIhHH4sI')


def _ordered_notes(data: bytes) -> bytes:
    # FL schedules a pattern's records chronologically across all channels.
    # A record earlier than its predecessor can disappear in the engine,
    # although a flat binary readback still sees every record.
    records = [data[i:i + NOTE.size] for i in range(0, len(data), NOTE.size)]
    records.sort(key=lambda record: (struct.unpack_from('<I', record)[0],
                                     struct.unpack_from('<H', record, 6)[0]))
    return b''.join(records)


def text(data: bytes) -> str:
    return data.decode('utf-16le').rstrip('\0')


def string(value: str) -> bytes:
    return (value + '\0').encode('utf-16le')


def wrapped_plugin(state):
    """Read the wrapper's sized UTF-8 identity records, leaving state opaque."""
    if state is None or len(state) < 4 or int.from_bytes(state[:4], 'little') not in (8, 10, 12):
        return None
    names, at = {}, 4
    while at + 12 <= len(state):
        tag, size = struct.unpack_from('<IQ', state, at)
        at += 12
        if size > len(state) - at: break
        if tag in (54, 55, 56):
            names[{54: 'name', 55: 'path', 56: 'vendor'}[tag]] = state[at:at + size].decode('utf-8', 'replace').rstrip('\0')
        elif tag == 52 and size == 16:
            names['class_id_hex'] = state[at:at + size].hex()
        at += size
    return names if names.get('name') else None


def preset_events(path: Path | str) -> list[Event]:
    preset = Project.read(path)
    legacy = int(preset.version.split('.')[0]) < 11
    result = []
    for event in preset.events:
        if event.id in (201, 203, 212, 213, 155, 128, 41):
            data = event.data
            if legacy and event.id in (201, 203):
                data = string(data.rstrip(b'\0').decode('cp1252'))
            result.append(Event(event.id, data))
    if not any(e.id == 201 for e in result) or not any(e.id == 213 for e in result):
        raise ValueError('Preset does not contain a complete generator/effect plugin state')
    return result


@dataclass(slots=True)
class Event:
    id: int
    data: bytes
    original: bytes | None = None
    original_size: int = 0

    def encode(self) -> bytes:
        if self.original is not None and self.original[0] == self.id and len(self.data) == self.original_size:
            return self.original + self.data
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
        self._channel_cache = None
        failures = []
        for size172 in (1, 4):
            try:
                events, version = self._parse_events(blob, size172)
                if self.format == 0 and sum(e.id == 64 for e in events) != self.channel_count:
                    raise ValueError('Channel identities do not match the FLhd count')
            except (ValueError, UnicodeError) as error:
                failures.append(str(error))
                continue
            self.events, self.version = events, version
            self.text_encoding = 'utf-16le' if version != 'unknown' and tuple(int(p) for p in version.split('.')[:2]) >= (11, 5) else 'latin-1'
            self.event_size_overrides = {172: size172} if any(e.id == 172 for e in events) else {}
            break
        else:
            raise ValueError('No consistent FLP event layout: ' + '; '.join(failures))

    @staticmethod
    def _parse_events(blob, size172):
        events = []
        append, event_type = events.append, Event
        end = len(blob)
        pos = 22
        version = 'unknown'
        while pos < end:
            event_start = pos
            eid = blob[pos]
            pos += 1
            if eid < 192:
                size = 1 if eid < 64 else 2 if eid < 128 else 4
                # One-byte event in actual FL25/26 files, despite its numeric
                # range. Select the layout by whole-stream/channel consistency.
                if eid == 172:
                    size = size172
            else:
                size = 0
                for shift in range(0, 35, 7):
                    if pos >= end:
                        raise ValueError('Truncated FLP variable length')
                    byte = blob[pos]
                    pos += 1
                    size |= (byte & 127) << shift
                    if not byte & 128:
                        break
                else:
                    raise ValueError('Invalid FLP variable length')
            if pos + size > end:
                raise ValueError(f'Truncated FLP event {eid}')
            head = blob[event_start:pos]
            data = blob[pos:pos + size]
            pos += size
            if eid == 199:
                version = data.rstrip(b'\0').decode('ascii')
            append(event_type(eid, data, head, size))
        return events, version

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
            elif start is not None and event.id in (65, 99, 100, 225, 233, 238):
                spans.append((start, index))
                start = None
        if start is not None:
            spans.append((start, len(self.events)))
        return spans

    def _text(self, data):
        return data.decode(self.text_encoding).rstrip('\0')

    def _string(self, value):
        return (value + '\0').encode(self.text_encoding)

    def channels(self) -> list[dict]:
        groups = [{e.id: e.data for e in self.events[start:end]} for start, end in self.channel_spans()]
        fields = (64, 21, 203, 192, 201, 196, 22, 104, 128, 219, 213)
        routes = [next((data for eid, data in reversed(group.items()) if eid in (22, 104)), b'\0') for group in groups]
        signature = tuple((*[group.get(field) for field in fields], route) for group, route in zip(groups, routes))
        if self._channel_cache is not None and self._channel_cache[0] == signature:
            return [dict(channel) for channel in self._channel_cache[1]]
        result = []
        for index, values in enumerate(groups):
            iid = int.from_bytes(values[64], 'little')
            levels = values.get(219)
            result.append({
                'index': index, 'iid': iid, 'name': self._text(values.get(203, values.get(192, values.get(201, b'\0\0')))),
                'type': values.get(21, b'\0')[0], 'plugin': self._text(values.get(201, b'\0\0')) or 'Sampler',
                'sample_path': self._text(values[196]) if 196 in values else None,
                'mixer_track': int.from_bytes(routes[index], 'little'),
                'color': int.from_bytes(values[128], 'little') if 128 in values else None,
                'volume_raw': struct.unpack_from('<I', levels, 4)[0] if levels and len(levels) >= 8 else None,
                'pan_raw': struct.unpack_from('<i', levels)[0] - 6400 if levels and len(levels) >= 4 else None,
                'plugin_state_sha256': hashlib.sha256(values[213]).hexdigest() if 213 in values else None,
                'wrapped_plugin': wrapped_plugin(values.get(213)) if self._text(values.get(201, b'\0\0')) == 'Fruity Wrapper' else None,
            })
        if len(result) != self.channel_count:
            raise ValueError('FLP channel count disagrees with the event section')
        self._channel_cache = signature, [dict(channel) for channel in result]
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
                patterns[current]['name'] = self._text(event.data)
            elif current is not None and event.id in (150, 164, 26):
                name = {150: 'color', 164: 'length_tick', 26: 'looped'}[event.id]
                value = int.from_bytes(event.data, 'little')
                patterns[current][name] = bool(value) if event.id == 26 else value
            elif current is not None and event.id == 224:
                if len(event.data) % NOTE.size:
                    raise ValueError(f'Unsupported note record size in pattern {current}')
                for record in NOTE.iter_unpack(event.data):
                    pos, flags, iid, length, key, group, fine, reserved, release, midi, pan, velocity, modx, mody = record
                    patterns[current]['notes'].append({
                        'channel_index': iid_to_index.get(iid), 'channel_iid': iid,
                        'key': key, 'start_tick': pos, 'length_tick': length, 'velocity': velocity,
                        'flags': flags, 'group': group, 'fine_pitch': fine, 'reserved_raw': reserved, 'release': release,
                        'midi_channel': midi, 'pan': pan, 'mod_x': modx, 'mod_y': mody,
                    })
            elif event.id in (64, 99):
                current = None
        return patterns

    def playlist_record_size(self) -> int:
        parts = tuple(int(x) for x in self.version.split('.')[:2])
        if parts >= (26, 0):
            return 88
        if parts >= (21, 2):
            return 80
        return 60 if parts >= (21, 0) else 32

    def playlist(self) -> list[dict]:
        from .timeline import read_playlist
        return read_playlist(self)

    @property
    def tempo(self) -> float:
        values = {e.id: e.data for e in self.events if e.id in (156, 66, 93)}
        if 156 in values: return int.from_bytes(values[156], 'little') / 1000
        return int.from_bytes(values.get(66, b'x\0'), 'little') + int.from_bytes(values.get(93, b'\0\0'), 'little') / 1000

    def inspect(self, include_notes=True, include_settings=False, sections=None) -> dict:
        from .automation import read_all
        from .fields import metadata, arrangements, pattern_controllers, channel_settings
        from .timing import markers
        result = {'path': str(self.path) if self.path else None, 'producer_version': self.version,
                'ppq': self.ppq, 'tempo_bpm': self.tempo,
                'event_count': len(self.events), 'source_sha256': hashlib.sha256(self.source).hexdigest()}
        readers = {'channels': self.channels, 'patterns': lambda: list(self.patterns().values()),
                   'playlist': self.playlist, 'mixer': self.mixer, 'automation': lambda: read_all(self),
                   'metadata': lambda: metadata(self), 'arrangements': lambda: arrangements(self),
                   'controllers': lambda: pattern_controllers(self), 'markers': lambda: markers(self),
                   'channel_settings': lambda: [channel_settings(self, i) for i in range(len(self.channel_spans()))]}
        selected = set(sections) if sections else set(readers) - {'channel_settings'}
        if include_settings: selected.add('channel_settings')
        if selected - readers.keys(): raise ValueError('Unknown inspection section')
        for name, reader in readers.items():
            if name in selected: result[name] = reader()
        for pattern in result.get('patterns', []):
            pattern['note_count'] = len(pattern['notes'])
            if not include_notes: pattern.pop('notes')
        return result

    def _replace_value(self, eid, data):
        for event in self.events:
            if event.id == eid:
                event.data = data
                return
        raise ValueError(f'Required FLP event {eid} not present')

    def set_tempo(self, bpm):
        if isinstance(bpm, bool) or not isinstance(bpm, (int, float)) or not math.isfinite(bpm) or not 10 <= bpm <= 999:
            raise ValueError('Tempo must be finite, 10..999 BPM')
        matches = [e for e in self.events if e.id == 156]
        if not matches:
            self.events.append(Event(156, struct.pack('<I', round(bpm * 1000))))
        else:
            for event in matches: event.data = struct.pack('<I', round(bpm * 1000))

    def replace_notes(self, pattern: int, channel_index: int, notes: list[dict], append=False):
        from .note_values import validate
        if type(pattern) is not int or not 1 <= pattern <= 999:
            raise ValueError('Pattern number must be 1..999')
        channels = self.channels()
        if type(channel_index) is not int or not 0 <= channel_index < len(channels):
            raise ValueError('Channel index is not in this saved project')
        iid = channels[channel_index]['iid']
        validated = [validate(n) for n in notes]
        additions = b''.join(NOTE.pack(n['start_tick'], n['flags'], iid, n['length_tick'], n['key'], n['group'],
                                       n['fine_pitch'], n['reserved_raw'], n['release'], n['midi_channel'], n['pan'], n['velocity'], n['mod_x'], n['mod_y']) for n in validated)
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
                event.data = _ordered_notes(kept + additions)
                return
        # Score blocks precede Channel Rack data. Metadata is a separate later section.
        start = self.channel_spans()[0][0]
        self.events[start:start] = [Event(65, struct.pack('<H', pattern)), Event(224, _ordered_notes(additions))]

    def name_pattern(self, number: int, name: str):
        current = None
        for event in self.events:
            if event.id == 65:
                current = int.from_bytes(event.data, 'little')
            elif event.id in (64, 99):
                current = None
            elif current == number and event.id == 193:
                event.data = self._string(name)
                return
        where = next(i for i, e in enumerate(self.events) if e.id == 99)
        self.events[where:where] = [Event(65, struct.pack('<H', number)), Event(193, self._string(name))]

    def set_playlist(self, clips: list[dict], arrangement=0):
        from .timeline import write_playlist
        write_playlist(self, clips, arrangement)

    def _set_fresh_playlist(self, clips: list[dict], event, record_size=None):
        size = record_size or self.playlist_record_size()
        records = []
        patterns = self.patterns()
        for uid, clip in enumerate(clips, 1):
            pat = clip.get('pattern_number')
            channel = clip.get('channel_index')
            track, pos, length = (clip[k] for k in ('track', 'start_tick', 'length_tick'))
            if any(type(x) is not int for x in (track, pos, length)) or not 1 <= track <= 500 or pos < 0 or length <= 0:
                raise ValueError('Playlist clip must reference an existing pattern and valid track/ticks')
            if (pat is None) == (channel is None):
                raise ValueError('Choose pattern_number or channel_index')
            if pat is not None:
                if type(pat) is not int or pat not in patterns:
                    raise ValueError('Playlist pattern is absent')
                item = 20480 + pat
            else:
                channels = self.channels()
                if type(channel) is not int or not 0 <= channel < len(channels) or channels[channel]['type'] not in (4, 5):
                    raise ValueError('Channel clip must reference an Audio Clip or Automation channel')
                item = channels[channel]['iid']
            record = struct.pack('<IHHIHHHH4sII', pos, 20480, item, length, 500 - track,
                                 clip.get('group', 0), 120, 64, bytes([64, 100, 128, 128]), 0xffffffff, 0xffffffff)
            if size >= 80:
                record += struct.pack('<I', uid) + bytes(28) + struct.pack('<d', 1.0) + bytes(8)
                if size == 88:
                    record += bytes(8)
            elif size == 60:
                record += struct.pack('<I', uid) + bytes(24)
            data = bytearray(record)
            kind = 'pattern' if channel is None else 'automation' if channels[channel]['type'] == 5 else 'audio'
            if kind == 'audio' and size >= 80:
                struct.pack_into('<f', data, 52, 1.0)
            from .timeline import initialize_window
            initialize_window(self, data, clip, kind)
            record = bytes(data)
            records.append(record)
        event.data = b''.join(sorted(records, key=lambda r: struct.unpack_from('<I', r)[0]))

    def set_channel(self, index: int, changes: dict):
        spans = self.channel_spans()
        if type(index) is not int or not 0 <= index < len(spans):
            raise ValueError('Channel index is not in this saved project')
        start, end = spans[index]
        mapping = {e.id: e for e in self.events[start:end]}
        for key, value in changes.items():
            if key == 'settings':
                from .fields import set_channel_settings
                set_channel_settings(self, index, value)
            elif key == 'kind':
                if value not in ('sampler', 'audio') or mapping[21].data[0] not in (0, 4):
                    raise ValueError('Sample channel kind must be sampler or audio')
                mapping[21].data = bytes([4 if value == 'audio' else 0])
            elif key == 'name':
                mapping[203].data = self._string(value)
            elif key == 'color':
                from .fields import patch
                data = patch(bytes(4), (0, 'I'), value)
                if 128 in mapping: mapping[128].data = data
                else: self.events.insert(start + 1, Event(128, data))
            elif key == 'muted':
                if type(value) is not bool:
                    raise ValueError('muted must be a boolean')
                mapping[0].data = bytes([not value])
            elif key == 'sample_path':
                sample = Path(value).resolve()
                if not sample.is_file():
                    raise ValueError(f'Sample does not exist: {sample}')
                mapping[196].data = self._string(str(sample))
            elif key == 'mixer_track':
                if type(value) is not int or not 0 <= value < len(self.mixer_spans()) - 1:
                    raise ValueError('Mixer route must identify an existing ordinary saved track; add the track first')
                if 104 in mapping:
                    mapping[104].data = struct.pack('<H', value)
                    if 22 in mapping:
                        if value < 256: mapping[22].data = bytes([value])
                        else: self.events[start:end] = [e for e in self.events[start:end] if e.id != 22]
                elif 22 in mapping and value < 256:
                    mapping[22].data = bytes([value])
                else:
                    self.events.insert(end, Event(104, struct.pack('<H', value)))
            elif key in ('volume_raw', 'pan_raw'):
                low, high = (0, 12800) if key == 'volume_raw' else (-6400, 6400)
                if type(value) is not int or not low <= value <= high:
                    raise ValueError(f'{key} must be {low}..{high}')
                raw = bytearray(mapping[219].data)
                # Keep the CLI's centered pan units consistent with Mixer.
                # Channel Levels stores 0..12800, with 6400 at the center.
                stored = value + 6400 if key == 'pan_raw' else value
                struct.pack_into('<I' if key == 'volume_raw' else '<i', raw, 4 if key == 'volume_raw' else 0, stored)
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
                # A complete new generator preset must not inherit the
                # previous preset's host parameter initializations.
                from .mixing import _erase_plugin_controls
                iid = int.from_bytes(mapping[64].data, 'little')
                _erase_plugin_controls(self, iid << 16)
            else:
                raise ValueError(f'Unsupported channel change: {key}')

    def mixer_spans(self):
        start = next((i + 1 for i, event in enumerate(self.events) if event.id == 100), len(self.events))
        spans = []
        for index in range(start, len(self.events)):
            if self.events[index].id == 147:
                spans.append((start, index + 1))
                start = index + 1
        # The installed factory projects store Master first, then ordinary
        # inserts, then Current. This is also the parameter-record order.
        return spans

    def mixer(self) -> list[dict]:
        tracks = []
        spans = self.mixer_spans()
        for start, end in spans:
            block = self.events[start:end]
            data = {e.id: e.data for e in block}
            plugins, plugin = [], None
            for e in block:
                if e.id == 201:
                    plugin = {'name': self._text(e.data), 'slot': None, 'state_sha256': None, 'wrapped_plugin': None}
                    plugins.append(plugin)
                elif plugin is not None and e.id == 213:
                    plugin['state_sha256'] = hashlib.sha256(e.data).hexdigest()
                    if plugin['name'] == 'Fruity Wrapper': plugin['wrapped_plugin'] = wrapped_plugin(e.data)
                elif plugin is not None and e.id == 98:
                    plugin['slot'] = int.from_bytes(e.data, 'little')
                    plugin = None
            default_name = 'Master' if not tracks else 'Current' if len(tracks) == len(spans) - 1 else f'Insert {len(tracks)}'
            tracks.append({'index': len(tracks), 'name': self._text(data[204]) if 204 in data else default_name,
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
                if event.data[offset + 5] == 31 and track is not None and track < len(tracks) and ident in (192, 193):
                    tracks[track]['volume_raw' if ident == 192 else 'pan_raw'] = value
        from .mixing import describe_mixer
        return describe_mixer(self, tracks)

    def _mixer_selectors(self):
        # Mixer REC addresses contain a host-specific prefix. Do not truncate
        # them to the old 7-bit PyFLP mask: FL's expanded mixer would alias them.
        values = []
        for event in self.events:
            if event.id == 225:
                for offset in range(0, len(event.data), 12):
                    if event.data[offset + 4:offset + 6] == b'\xc0\x1f':
                        values.append(struct.unpack_from('<H', event.data, offset + 6)[0] & 0xffc0)
        if len(values) != len(set(values)):
            raise ValueError('Ambiguous mixer parameter address list')
        return {selector: index for index, selector in enumerate(values)}

    def set_mixer(self, track: int, changes: dict):
        if type(track) is not int or not 0 <= track < len(self.mixer()) - 1:
            raise ValueError('Mixer index is not in this saved project')
        selectors = self._mixer_selectors()
        if 'sends' in changes and 'routes' in changes:
            if any(s.get('to') not in changes['routes'] for s in changes['sends']):
                raise ValueError('Explicit sends must belong to the explicit routes array')
        ordered = [(key, value) for key, value in changes.items() if key != 'sends']
        if 'sends' in changes:
            ordered.append(('sends', changes['sends']))
        for key, value in ordered:
            if key in ('polarity_reversed', 'channels_swapped', 'threaded_processing', 'solo',
                       'hardware_input_raw', 'hardware_output_raw', 'eq'):
                from .mixing import set_track_field
                set_track_field(self, track, key, value)
                continue
            if key == 'sends':
                from .mixing import set_sends
                set_sends(self, track, value)
                continue
            if key in ('name', 'muted', 'routes', 'effects_enabled'):
                start, end = self.mixer_spans()[track]
                block = {e.id: e for e in self.events[start:end]}
                if key == 'name':
                    if 204 in block:
                        block[204].data = self._string(value)
                    else:
                        self.events.insert(start, Event(204, self._string(value)))
                elif key in ('muted', 'effects_enabled'):
                    if type(value) is not bool:
                        raise ValueError(f'{key} must be a boolean')
                    data = bytearray(block[236].data)
                    flags = struct.unpack_from('<I', data, 4)[0]
                    bit, enabled = (8, not value) if key == 'muted' else (4, value)
                    struct.pack_into('<I', data, 4, flags | bit if enabled else flags & ~bit)
                    block[236].data = bytes(data)
                else:
                    if not isinstance(value, list) or any(type(x) is not int or not 0 <= x < len(self.mixer()) - 1 or x == track for x in value):
                        raise ValueError('routes must contain other ordinary mixer indices')
                    data = bytes(int(i in value) for i in range(max([0, *value]) + 1))
                    if 235 in block:
                        block[235].data = data
                    else:
                        self.events.insert(end - 1, Event(235, data))
                    from .mixing import initial_values, send_address, set_initial
                    old_values = initial_values(self)
                    for destination in value:
                        address = send_address(self, track, destination)
                        if address not in old_values:
                            set_initial(self, address, 12800)
                continue
            if key not in ('volume_raw', 'pan_raw'):
                raise ValueError(f'Unsupported mixer change: {key}')
            low, high = (0, 16000) if key == 'volume_raw' else (-6400, 6400)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{key} must be {low}..{high}')
            from .mixing import initial_values, set_initial, track_address
            address = track_address(self, track) | (192 if key == 'volume_raw' else 193)
            if address not in initial_values(self):
                raise ValueError('Mixer parameter is absent; refusing to invent a host event')
            set_initial(self, address, value)

    def load_effect(self, track: int, slot: int, preset: Path | str | list[Event], *, links_prepared=False):
        if type(slot) is not int or not 0 <= slot < 10:
            raise ValueError('Effect slot must be 0..9')
        spans = self.mixer_spans()
        if type(track) is not int or not 0 <= track < len(spans) - 1:
            raise ValueError('Mixer track is absent')
        if not links_prepared:
            from .mixing import _chain_links, slot_address
            _chain_links(self, set(), {}, {slot_address(self, track, slot) >> 16})
        start, end = spans[track]
        position = start
        for i in range(start, end):
            event = self.events[i]
            if event.id == 98:
                if int.from_bytes(event.data, 'little') == slot:
                    existing = self.events[position:i]
                    keep = [e for e in existing if e.id not in (201, 203, 212, 213, 155, 128, 41)]
                    plugin = ([Event(e.id, e.data) for e in preset] if isinstance(preset, list)
                              else preset_events(preset))
                    for item in plugin:
                        if item.id == 212:
                            if len(item.data) < 8:
                                raise ValueError('Effect preset has no host track/slot address')
                            # An FST retains its original host address. Merely
                            # placing its events in another insert still loads
                            # it on that old track (often Master).
                            data = bytearray(item.data)
                            struct.pack_into('<II', data, 0, track, slot)
                            item.data = bytes(data)
                    self.events[position:i] = keep + plugin
                    from .mixing import _erase_plugin_controls, slot_address, set_initial
                    base = slot_address(self, track, slot)
                    _erase_plugin_controls(self, base)
                    set_initial(self, base, 1)
                    set_initial(self, base | 1, 12800)
                    return
                position = i + 1
        raise ValueError('Effect slot was not found in the mixer profile')

    def effect_events(self, track: int, slot: int) -> list[Event]:
        self._effect_state(track, slot)
        start, end = self.mixer_spans()[track]
        position = start
        for index in range(start, end):
            event = self.events[index]
            if event.id == 98:
                if int.from_bytes(event.data, 'little') == slot:
                    return [Event(e.id, e.data) for e in self.events[position:index]
                            if e.id in (201, 203, 212, 213, 155, 128, 41)]
                position = index + 1
        raise ValueError('Effect slot is absent')

    def _effect_state(self, track: int, slot: int):
        spans = self.mixer_spans()
        if type(track) is not int or not 0 <= track < len(spans) - 1 or type(slot) is not int or not 0 <= slot < 10:
            raise ValueError('Choose an existing mixer track and slot 0..9')
        start, end = spans[track]
        name, state = None, None
        for event in self.events[start:end]:
            if event.id == 201:
                    name, state = self._text(event.data), None
            elif event.id == 213:
                state = event
            elif event.id == 98:
                if int.from_bytes(event.data, 'little') == slot:
                    if name is None or state is None:
                        raise ValueError('Effect slot is empty')
                    return name, state
                name, state = None, None
        raise ValueError('Effect slot is absent')

    def plugin_parameters(self, track: int, slot: int) -> dict:
        name, state = self._effect_state(track, slot)
        # This profile is backed by matching FL native-save and live API
        # values. Unknown plugin blobs remain opaque rather than guessed.
        if name != 'Emphasizer' or len(state.data) != 29 or state.data[:4] != struct.pack('<I', 2):
            from .plugin_profiles import parameters
            return parameters(self, track, slot)
        value = struct.unpack_from('<I', state.data, 8)[0] / 10000
        return {'track': track, 'slot': slot, 'plugin': name,
                'params': [{'i': 1, 'name': 'Emphasis', 'v': value}],
                'limitations': ['Saved-state profile exposes Emphasis only; live API lists other host parameters']}

    def set_plugin_parameter(self, track: int, slot: int, param: str, value: float) -> dict:
        before = self.plugin_parameters(track, slot)
        if param != 'Emphasis' or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Saved-state profile accepts Emphasis with a finite normalized value 0..1')
        _, state = self._effect_state(track, slot)
        data = bytearray(state.data)
        struct.pack_into('<I', data, 8, round(value * 10000))
        state.data = bytes(data)
        return {'before': before, 'after': self.plugin_parameters(track, slot)}


def create_project(spec: dict, template: Path) -> Project:
    """Create a Sampler project from a real installed empty/basic template."""
    project = Project.read(template)
    spans = project.channel_spans()
    source = next((project.events[a:b] for a, b in spans
                   if any(e.id == 196 for e in project.events[a:b])), None)
    if not source:
        raise ValueError('Template must contain a Sampler channel')
    channels = spec['channels']
    if not 1 <= len(channels) <= 4096:
        raise ValueError('A project needs 1..4096 channels')
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
            elif event.id == 21 and channel.get('kind') == 'audio':
                if not sample:
                    raise ValueError('Audio Clip channels require a sample')
                data = b'\x04'
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
    # New compositions open on an actual pattern and render their Playlist,
    # rather than inheriting the factory template's empty Pattern-mode export.
    project._replace_value(67, struct.pack('<H', spec['patterns'][0]['number'] if spec['patterns'] else 1))
    project._replace_value(9, b'\x01')
    project.set_playlist(spec['playlist'])
    for mixer in spec.get('mixer', []):
        project.set_mixer(mixer['track'], {k: v for k, v in mixer.items() if k != 'track'})
    for effect in spec.get('effects', []):
        project.load_effect(effect['track'], effect['slot'], effect['preset'])
    from .mixing import apply_chains, validate_routing
    apply_chains(project, spec.get('fx_chains', []))
    from .sytrus import set_parameters
    for synth in spec.get('sytrus', []):
        set_parameters(project, synth['channel'], synth['params'])
    from .plugin_profiles import apply_parameters
    apply_parameters(project, spec.get('plugin_params', []))
    from .automation import create_curve
    for curve in spec.get('automation', []):
        create_curve(project, curve)
    validate_routing(project)
    return project
