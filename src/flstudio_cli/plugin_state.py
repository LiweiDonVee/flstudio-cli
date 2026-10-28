"""Local, typed edits of known plugin fields; retain all unedited state bytes."""
from __future__ import annotations

import struct


WRAPPER_FLAGS = {'smart_disable': 0x20, 'threaded_processing': 0x40}
VST_FLAGS = {
    'send_pitch_bend_range': (1, True), 'fixed_size_buffers': (2, True),
    'notify_render': (4, True), 'process_inactive_io': (8, True),
    'send_release_velocity': (0x20, False), 'notify_parameter_changes': (0x40, False),
    'send_loop_position': (0x800, True), 'allow_threaded_processing': (0x1000, True),
    'ensure_processor_state': (0x10000, False), 'send_mod_x_as_aftertouch': (0x20000, True),
    'load_bridged': (0x40000, True), 'external_window': (0x200000, True),
    'reset_on_transport': (0x2000000, False), 'allow_smart_disable': (0x20000000, True),
    'use_time_offset': (0x80000000, False),
}
NATIVE = {
    'BooBass': ((12, 16), ('bass_raw', 'mid_raw', 'high_raw'), 'III'),
    'Fruit Kick': ((32, 400), ('unknown_header', 'max_frequency_raw', 'min_frequency_raw',
                         'frequency_decay_raw', 'amplitude_decay_raw', 'click_raw', 'distortion_raw'), 'IiiIIII'),
    'Plucked!': ((20,), ('decay_raw', 'color_raw', 'normalize', 'gate', 'widen'), 'II???'),
    'Fruity Balance': ((8,), ('pan_raw', 'volume_raw'), 'iI'),
    'Fruity Blood Overdrive': ((32, 36), ('pre_band_raw', 'color_raw', 'pre_amp_raw',
                                      'x100', 'post_filter_raw', 'post_gain_raw'), 'III?II'),
    'Fruity Center': ((4, 8), ('enabled',), '?'),
    'Fruity Fast Dist': ((20,), ('pre_raw', 'threshold_raw', 'kind_raw', 'mix_raw', 'post_raw'), 'IIIII'),
    'Fruity Send': ((16,), ('pan_raw', 'dry_raw', 'volume_raw', 'destination_raw'), 'iIIi'),
    'Fruity Stereo Enhancer': ((24,), ('pan_raw', 'volume_raw', 'separation_raw',
                                   'phase_offset_raw', 'effect_position_raw', 'inversion_raw'), 'iIIIII'),
    'Soundgoodizer': ((8, 12), ('mode_raw', 'amount_raw'), 'II'),
}


def events(project, target):
    if set(target) == {'channel'}:
        index = target['channel']
        spans = project.channel_spans()
        if type(index) is not int or not 0 <= index < len(spans): raise ValueError('Channel is absent')
        a, b = spans[index]
    elif set(target) == {'track', 'slot'}:
        from .mixing import _slot_span
        a, b = _slot_span(project, target['track'], target['slot'])
    else: raise ValueError('Choose channel or track+slot')
    block = {e.id: e for e in project.events[a:b] if e.id in (201, 212, 213)}
    if 201 not in block or 213 not in block: raise ValueError('Target has no plugin state')
    return project._text(block[201].data), block


def _native_fields(name, data):
    schema = NATIVE.get(name)
    if not schema or len(data) not in schema[0]: return {}
    sizes, names, types = schema
    base = 4 if name in ('BooBass', 'Fruity Blood Overdrive', 'Fruity Center', 'Soundgoodizer') and len(data) == max(sizes) and len(sizes) > 1 else 0
    return {key: (base + index * 4, kind) for index, (key, kind) in enumerate(zip(names, types))
            if key != 'unknown_header'}


def _notebook(data):
    if len(data) < 13: raise ValueError('Truncated Notebook 2 state')
    at, pages = 8, []
    while at + 4 <= len(data):
        index = struct.unpack_from('<i', data, at)[0]; at += 4
        if index == -1:
            if at >= len(data): raise ValueError('Notebook editable field is absent')
            return pages, at, struct.unpack_from('<I', data, 4)[0], bool(data[at])
        length, shift = 0, 0
        while True:
            if at >= len(data) or shift > 28: raise ValueError('Invalid Notebook text length')
            byte = data[at]; at += 1; length |= (byte & 127) << shift
            if byte < 128: break
            shift += 7
        end = at + length * 2
        if end > len(data): raise ValueError('Truncated Notebook page')
        pages.append({'index': index, 'text': data[at:end].decode('utf-16le')}); at = end
    raise ValueError('Notebook page terminator is absent')


def describe(project, target):
    name, block = events(project, target)
    data = block[213].data
    result = {**target, 'plugin': name, 'state_bytes': len(data), 'wrapper': {}, 'native': {}}
    common = block.get(212)
    if common and len(common.data) >= 18:
        flags = struct.unpack_from('<H', common.data, 16)[0]
        result['wrapper'] = {key: bool(flags & mask) for key, mask in WRAPPER_FLAGS.items()}
        result['wrapper']['generator'] = bool(flags & 0x10)
    if name == 'Fruity Wrapper' and len(data) >= 4 and struct.unpack_from('<I', data)[0] in (8, 10, 12):
        at, records = 4, []
        while at + 12 <= len(data):
            tag, size = struct.unpack_from('<IQ', data, at); at += 12
            if size > len(data) - at: break
            value = data[at:at + size]; records.append({'tag': tag, 'bytes': size})
            if tag == 1 and size >= 12:
                result['vst_midi'] = dict(zip(('input_port', 'output_port', 'pitch_bend_range'), struct.unpack_from('<iiI', value)))
            elif tag == 2 and size >= 23:
                flags, flags2 = struct.unpack_from('<II', value, 9)
                result['vst_processing'] = {key: bool(flags & mask) == positive for key, (mask, positive) in VST_FLAGS.items()}
                result['vst_processing'].update(process_maximum=bool(flags2 & 1), use_maximum_from_host=bool(flags2 & 2), fast_idle=bool(value[22]))
            at += size
        result['vst_records'] = records
    for key, (offset, kind) in _native_fields(name, data).items():
        result['native'][key] = bool(struct.unpack_from('<I', data, offset)[0]) if kind == '?' else struct.unpack_from('<' + kind, data, offset)[0]
    if name == 'Fruity NoteBook 2':
        pages, _, active, editable = _notebook(data)
        result['notebook'] = {'active_page': active, 'editable': editable, 'pages': pages}
    return result


def edit(project, spec):
    if not isinstance(spec, dict): raise ValueError('Plugin settings require an object')
    target = {k: spec[k] for k in ('channel', 'track', 'slot') if k in spec}
    if set(spec) - set(target) - {'wrapper', 'native', 'notebook'}: raise ValueError('Unknown plugin setting group')
    name, block = events(project, target)
    before = describe(project, target)
    if 'wrapper' in spec:
        changes = spec['wrapper']; common = block.get(212)
        if not isinstance(changes, dict) or set(changes) - WRAPPER_FLAGS.keys(): raise ValueError('Only common smart_disable and threaded_processing flags are writable')
        if not common or len(common.data) < 18: raise ValueError('Wrapper flags are absent')
        data = bytearray(common.data); flags = struct.unpack_from('<H', data, 16)[0]
        for key, value in changes.items():
            if type(value) is not bool: raise ValueError('Wrapper flags require booleans')
            mask = WRAPPER_FLAGS[key]; flags = flags | mask if value else flags & ~mask
        struct.pack_into('<H', data, 16, flags); common.data = bytes(data)
    if 'native' in spec:
        fields, changes = _native_fields(name, block[213].data), spec['native']
        if not isinstance(changes, dict) or set(changes) - fields.keys(): raise ValueError('Unknown raw field or unsupported native plugin state layout')
        data = bytearray(block[213].data)
        for key, value in changes.items():
            offset, kind = fields[key]
            if kind == '?' and type(value) is not bool or kind != '?' and type(value) is not int: raise ValueError('Raw fields require integers; switches require booleans')
            try: struct.pack_into('<I' if kind == '?' else '<' + kind, data, offset, value)
            except struct.error as error: raise ValueError(str(error)) from None
        block[213].data = bytes(data)
    if 'notebook' in spec:
        if name != 'Fruity NoteBook 2': raise ValueError('Notebook fields require Fruity NoteBook 2')
        changes = spec['notebook']
        if not isinstance(changes, dict) or set(changes) - {'pages', 'active_page', 'editable'}: raise ValueError('Unknown Notebook field')
        original = block[213].data; pages, end, active, editable = _notebook(original)
        patches = changes.get('pages', [])
        if not isinstance(patches, list): raise ValueError('Notebook pages must be an array')
        seen = set()
        for page in patches:
            if (not isinstance(page, dict) or set(page) != {'index', 'text'} or type(page['index']) is not int
                    or not 0 <= page['index'] <= 100 or not isinstance(page['text'], str) or page['index'] in seen): raise ValueError('Each unique page requires index 0..100 and text')
            seen.add(page['index'])
            existing = next((p for p in pages if p['index'] == page['index']), None)
            if existing is None: pages.append(dict(page))
            else: existing['text'] = page['text']
        active, editable = changes.get('active_page', active), changes.get('editable', editable)
        if type(active) is not int or not 0 <= active <= 100 or type(editable) is not bool: raise ValueError('Choose active_page 0..100 and boolean editable')
        data = bytearray(original[:4] + struct.pack('<I', active))
        for page in pages:
            raw = page['text'].encode('utf-16le'); length = len(raw) // 2
            data += struct.pack('<i', page['index'])
            while length >= 128: data.append((length & 127) | 128); length >>= 7
            data.append(length); data += raw
        data += struct.pack('<i', -1) + bytes([editable]) + original[end + 1:]
        block[213].data = bytes(data)
    return {'before': before, 'after': describe(project, target)}
