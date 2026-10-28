"""Named native effect host controls; opaque preset bytes stay untouched."""
from __future__ import annotations

import struct

from .mixing import initial_values, set_initial, slot_address


def profile(name: str, state: bytes) -> list[dict]:
    entries = []
    def add(param, index, low, high, unit='native_raw'):
        entries.append({'param': param, 'index': index, 'minimum': low, 'maximum': high, 'unit': unit})
    if name == 'Fruity Parametric EQ 2' and len(state) == 354 and struct.unpack_from('<I', state)[0] == 8:
        for band in range(1, 8):
            add(f'band{band}.gain', band - 1, -1800, 1800, 'centidB')
            add(f'band{band}.frequency', band + 6, 0, 65536)
            add(f'band{band}.width', band + 13, 0, 65536)
            add(f'band{band}.type', band + 20, 0, 7, 'enum')
            add(f'band{band}.order', band + 27, -3, 3, 'enum')
        add('main_level', 35, -1800, 1800, 'centidB')
    elif name == 'Fruity Reeverb 2' and len(state) == 66 and struct.unpack_from('<I', state)[0] == 10001:
        for param, index, low, high in (
            ('low_cut', 0, 19, 3000), ('high_cut', 1, 5, 221), ('predelay', 2, 0, 384),
            ('room_size', 3, 1, 100), ('diffusion', 4, 0, 100), ('decay', 5, 1, 200),
            ('high_damping', 6, 5, 221), ('bass', 7, 20, 300), ('crossover', 8, 25, 2000),
            ('stereo', 9, -64, 64), ('dry', 10, 0, 160), ('early_reflections', 11, 0, 160),
            ('wet', 12, 0, 160), ('mod_speed', 13, 0, 2048), ('mod_depth', 14, 0, 2048)):
            add(param, index, low, high)
    elif name == 'Fruity Reeverb 2' and len(state) == 53:
        for param, index, low, high in (
            ('high_cut', 0, 0, 100), ('low_cut', 1, 0, 100), ('predelay', 2, 0, 1000),
            ('room_size', 3, 0, 100), ('diffusion', 4, 0, 100), ('decay', 5, 0, 200),
            ('high_damping', 6, 0, 100), ('bass', 7, 0, 400), ('crossover', 8, 0, 2000),
            ('stereo', 9, -64, 64), ('dry', 10, 0, 128), ('early_reflections', 11, 0, 128),
            ('wet', 12, 0, 128)):
            add(param, index, low, high)
    elif name.casefold() == 'fruity soft clipper' and len(state) == 8:
        add('threshold', 0, 1, 127)
        add('post_gain', 1, 0, 160)
    elif name == 'Fruity Limiter' and len(state) == 161 and struct.unpack_from('<I', state)[0] == 5:
        add('gain', 0, 0, 10000)
        add('ceiling', 2, 0, 1000)
    elif name == 'Fruity Limiter' and len(state) == 169 and struct.unpack_from('<I', state)[0] == 7:
        for param, index, low, high in (
            ('gain', 0, 0, 2000), ('saturation_threshold', 1, 0, 1000), ('ceiling', 2, 0, 2000),
            ('limiter_attack', 3, 0, 10000), ('limiter_attack_curve', 4, 1, 8),
            ('limiter_release', 5, 0, 10000), ('limiter_release_curve', 6, 1, 8),
            ('peak_window', 7, 0, 10000), ('comp_threshold', 8, 0, 1000),
            ('comp_ratio', 9, -1000, 1000), ('comp_knee', 10, -1000, 1000),
            ('comp_attack', 11, 0, 10000), ('comp_release', 12, 0, 10000),
            ('comp_curve', 13, 1, 8), ('comp_rms_window', 14, 0, 10000),
            ('gate_gain', 15, 0, 1000), ('gate_threshold', 16, 0, 1000), ('gate_release', 17, 0, 10000)):
            add(param, index, low, high)
    return entries


def parameters(project, track, slot) -> dict:
    name, state = project._effect_state(track, slot)
    entries = profile(name, state.data)
    if not entries:
        raise ValueError('No saved host-control profile for this effect state; use live plugin-params')
    base = (slot_address(project, track, slot) & 0xffff0000) | 0x8000
    values = initial_values(project)
    return {'track': track, 'slot': slot, 'plugin': name,
            'params': [{**entry, 'value_raw': values.get(base + entry['index']),
                        'value_source': 'saved_host_override' if base + entry['index'] in values else 'opaque_preset'}
                       for entry in entries],
            'limitations': ['Null means the unchanged preset owns this value, not zero',
                            'Raw native units differ from normalized live API values']}


def set_parameter(project, track, slot, param, value):
    before = parameters(project, track, slot)
    matches = [p for p in before['params'] if p['param'] == param or type(param) is int and p['index'] == param]
    if len(matches) != 1:
        raise ValueError('Choose a named saved native control or its listed index')
    target = matches[0]
    if type(value) is not int or not target['minimum'] <= value <= target['maximum']:
        raise ValueError(f'{target["param"]} value_raw must be an integer {target["minimum"]}..{target["maximum"]}')
    base = (slot_address(project, track, slot) & 0xffff0000) | 0x8000
    set_initial(project, base + target['index'], value)
    return {'before': target, 'after': {**target, 'value_raw': value, 'value_source': 'saved_host_override'}}


def apply_parameters(project, changes):
    from .sytrus import set_parameters
    if not isinstance(changes, list):
        raise ValueError('plugin_params must be an array')
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError('Each plugin parameter must be an object')
        target = {'channel'} if 'channel' in change else {'track', 'slot'}
        value = {'value_raw'} if 'value_raw' in change else {'value'}
        if set(change) != target | value | {'param'}:
            raise ValueError('Choose channel or track+slot, param, and exactly one value or value_raw')
        if target == {'channel'}:
            if value != {'value_raw'}:
                raise ValueError('Saved Sytrus controls require value_raw; normalized value is live-only')
            set_parameters(project, change['channel'], [{'param': change['param'], 'value_raw': change['value_raw']}])
        elif value == {'value_raw'}:
            set_parameter(project, change['track'], change['slot'], change['param'], change['value_raw'])
        else:
            project.set_plugin_parameter(change['track'], change['slot'], change['param'], change['value'])
