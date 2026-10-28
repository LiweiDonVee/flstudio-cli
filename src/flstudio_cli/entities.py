"""Clone FL-authored entities, retaining their complete event blocks."""
from __future__ import annotations

import struct

from .flp import Event, NOTE, _ordered_notes


def pattern_blocks(project, number):
    start, current = None, None
    for i, event in enumerate(project.events):
        if event.id in (65, 64, 99, 225, 236):
            if start is not None and current == number: yield start, i
            start, current = (i, int.from_bytes(event.data, 'little')) if event.id == 65 else (None, None)
    if start is not None and current == number: yield start, len(project.events)


def copy_events(events):
    return [Event(e.id, e.data, e.original, e.original_size) for e in events]


def pattern_insertion(project):
    return next((i for i, e in enumerate(project.events) if e.id in (64, 99, 100, 225, 233, 236)), len(project.events))


def edit_pattern(project, spec):
    allowed = {'number', 'name', 'clone_from', 'color', 'length_tick', 'looped'}
    if not isinstance(spec, dict) or set(spec) - allowed or type(spec.get('number')) is not int or not 1 <= spec['number'] <= 999:
        raise ValueError('Pattern requires number 1..999 and supported properties')
    number = spec['number']; patterns = project.patterns()
    if 'clone_from' in spec:
        source = spec['clone_from']
        if source not in patterns or number in patterns: raise ValueError('Clone requires an existing source and an unused pattern number')
        clone = [e for a, b in pattern_blocks(project, source) for e in copy_events(project.events[a:b])]
        for event in clone:
            if event.id == 65: event.data = struct.pack('<H', number)
        at = pattern_insertion(project)
        project.events[at:at] = clone
    elif number not in patterns:
        at = pattern_insertion(project)
        project.events[at:at] = [Event(65, struct.pack('<H', number))]
    if 'name' in spec:
        if not isinstance(spec['name'], str): raise ValueError('Pattern name requires text')
        names = [e for a, b in pattern_blocks(project, number) for e in project.events[a:b] if e.id == 193]
        if names:
            for event in names: event.data = project._string(spec['name'])
        else:
            a, _ = next(pattern_blocks(project, number)); project.events.insert(a + 1, Event(193, project._string(spec['name'])))
    from .fields import patch
    for name, eid, fmt in (('color', 150, 'I'), ('length_tick', 164, 'I'), ('looped', 26, '?')):
        if name not in spec: continue
        data = patch(bytes(struct.calcsize('<' + fmt)), (0, fmt), spec[name])
        existing = [e for a, b in pattern_blocks(project, number) for e in project.events[a:b] if e.id == eid]
        if existing:
            for event in existing: event.data = data
        else:
            a, _ = next(pattern_blocks(project, number)); project.events.insert(a + 1, Event(eid, data))


def clone_channel(project, source, name=None, copy_scores=False):
    channels = project.channels()
    if type(source) is not int or not 0 <= source < len(channels): raise ValueError('Clone source channel is absent')
    if type(copy_scores) is not bool: raise ValueError('copy_scores must be boolean')
    original = channels[source]
    if original['type'] == 5: raise ValueError('Use automation create with an explicit target for linked automation')
    iid = max(ch['iid'] for ch in channels) + 1
    if iid >= 4096: raise ValueError('No free channel identity remains')
    spans = project.channel_spans(); a, b = spans[source]; block = copy_events(project.events[a:b])
    for event in block:
        if event.id == 64: event.data = struct.pack('<H', iid)
    label = name if name is not None else original['name'] + ' copy'
    if not isinstance(label, str) or not label: raise ValueError('Channel name must be nonempty text')
    names = [e for e in block if e.id == 203]
    if names:
        for event in names: event.data = project._string(label)
    else: block.insert(1, Event(203, project._string(label)))
    at = spans[-1][1]; project.events[at:at] = block; project.channel_count += 1
    for event in project.events:
        if event.id in (216, 225) and len(event.data) % 12 == 0:
            additions = []
            for offset in range(0, len(event.data), 12):
                address = struct.unpack_from('<I', event.data, offset + 4)[0]
                if address >> 16 == original['iid']:
                    record = bytearray(event.data[offset:offset + 12]); struct.pack_into('<I', record, 4, iid << 16 | (address & 0xffff)); additions.append(record)
            event.data += b''.join(additions)
        if copy_scores and event.id == 224:
            additions = []
            for offset in range(0, len(event.data), NOTE.size):
                if struct.unpack_from('<H', event.data, offset + 6)[0] == original['iid']:
                    record = bytearray(event.data[offset:offset + NOTE.size]); struct.pack_into('<H', record, 6, iid); additions.append(record)
            if additions: event.data = _ordered_notes(event.data + b''.join(additions))
        if copy_scores and event.id == 223:
            additions = []
            for offset in range(0, len(event.data), 12):
                address = struct.unpack_from('<I', event.data, offset + 4)[0]
                if address >> 16 == original['iid']:
                    record = bytearray(event.data[offset:offset + 12]); struct.pack_into('<I', record, 4, iid << 16 | (address & 0xffff)); additions.append(record)
            event.data += b''.join(additions)
    return len(channels)
