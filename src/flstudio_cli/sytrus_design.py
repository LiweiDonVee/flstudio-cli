"""Calibrated Sytrus Default-family state editing for FL 26.1.6.

These fields are outside the host automation catalog. Layouts are admitted by
exact serialization profiles plus repeated numeric structure guards. Every
other byte, including unknown operator and envelope data, is retained.
"""
from __future__ import annotations

import math
from pathlib import Path
import struct
import zlib

from .flp import Project

INSTALL = Path('C:/Program Files/Image-Line/FL Studio 2026')
# The four opaque prefix bytes are matched, never interpreted as a version.
PROFILES = (
    {'name': 'factory-default-legacy', 'prefix': bytes.fromhex('13000000'),
     'size': 64854, 'operator_base': 1443, 'operator_stride': 6976,
     'envelope_version': 2, 'volume_header': 2936, 'filter_base':43299, 'filter_stride':6633, 'articulator_stride':808},
    {'name': 'fl26-native-default', 'prefix': bytes.fromhex('03001900'),
     'size': 64871, 'operator_base': 1210, 'operator_stride': 7000,
     'envelope_version': 3, 'volume_header': 2940, 'filter_base':43210, 'filter_stride':6665, 'articulator_stride':812},
)
NODE = struct.Struct('<ddfI')
LIMITATIONS = [
    'Only the installed Default.fst family and its FL 26.1.6 native saves are admitted.',
    'FM/RM operator modulation is separate from shared OP-to-filter, FX/OUT sends and PAN; filter-to-filter sends are not matrix edges.',
    'Only the first 32 harmonic coefficient slots are exposed; phase and the remaining waveform data are preserved.',
    'Volume envelope edits retain four points, curve tensions and loop/sustain markers; supplied envelopes enable by default.',
    'Envelope time_raw is the native serialized segment duration, not an asserted seconds value.',
    'Structural readback is distinct from native reopen and audible acceptance.',
]


def _number(value, low, high, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be a finite number {low}..{high}')
    return float(value)


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer {low}..{high}')
    return value


def _target(project, channel):
    channels = project.channels()
    if type(channel) is not int or not 0 <= channel < len(channels):
        raise ValueError('Choose an existing global saved channel index')
    if channels[channel]['plugin'].casefold() != 'sytrus':
        raise ValueError('Sytrus design requires a Sytrus channel; use init=true to install the local Default preset')
    start, end = project.channel_spans()[channel]
    found = [event for event in project.events[start:end] if event.id == 213]
    if len(found) != 1:
        raise ValueError('Sytrus must contain exactly one private state event')
    return found[0]


def _decode(blob):
    if len(blob) < 6:
        raise ValueError('Sytrus private state is missing or truncated')
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(blob[4:], 1024 * 1024)
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('Unsupported Sytrus compressed state envelope')
    except zlib.error as error:
        raise ValueError('Sytrus private state is not a supported compressed profile') from error
    profile = next((p for p in PROFILES if blob[:4] == p['prefix'] and len(raw) == p['size']), None)
    if profile is None:
        raise ValueError('Unsupported Sytrus state profile; initialize from the locally installed Default.fst')
    # Independent guards in all six operators distinguish these calibrated
    # layouts from equally-sized arbitrary states. Edits to admitted fields do
    # not affect these anchors.
    version = profile['envelope_version']
    first_header = struct.pack('<iiffiii', version, 0, 1.0, 1.0, 1, version, 4)
    shape_neighbors = struct.pack('<6i', 0, 0, 0, 128, 0, 0)
    for operator in range(6):
        base = profile['operator_base'] + operator * profile['operator_stride']
        volume = base + profile['volume_header']
        if (raw[base+2104:base+2128] != shape_neighbors or
                raw[base+2128:base+2156] != first_header or
                raw[volume:volume+28] != first_header):
            raise ValueError(f'Sytrus operator {operator+1} does not match the calibrated Default-family layout')
        ratio = struct.unpack_from('<i', raw, base+40)[0]
        shape = struct.unpack_from('<i', raw, base+2100)[0]
        if not 0 <= ratio <= 640000 or not 0 <= shape <= 512:
            raise ValueError('Sytrus operator fields are outside the calibrated native ranges')
        for at in range(32):
            coefficient = struct.unpack_from('<f', raw, base+52+at*4)[0]
            if not math.isfinite(coefficient) or not 0 <= coefficient <= 1:
                raise ValueError('Sytrus harmonic coefficients are outside the admitted profile')
        for point in range(4):
            duration, level, tension, flags = NODE.unpack_from(raw, volume+28+point*NODE.size)
            if (not all(math.isfinite(v) for v in (duration, level, tension)) or
                    not 0 <= duration <= 10000 or not 0 <= level <= 1):
                raise ValueError('Sytrus volume envelope differs from the calibrated four-point profile')
        if struct.unpack_from('<i', raw, volume+128)[0] not in (0, -1):
            raise ValueError('Sytrus volume envelope enabled flag differs from the calibrated profile')
    return profile, bytearray(raw)


def _filter_header(profile, number):
    return profile['filter_base']+(number-1)*profile['filter_stride']+169+2*profile['articulator_stride']


def _cutoff_view(profile, raw, number):
    at=_filter_header(profile,number)
    expected=struct.pack('<iiffiii',profile['envelope_version'],0,1.,1.,1,profile['envelope_version'],4)
    scales=struct.unpack_from('<ff',raw,at+8)
    if (raw[at:at+8]!=expected[:8] or raw[at+16:at+28]!=expected[16:] or
            any(not math.isfinite(v) or not 0<=v<=2 for v in scales) or struct.unpack_from('<i',raw,at+128)[0] not in (0,-1)):
        raise ValueError('Unsupported Sytrus filter cutoff envelope layout; use the calibrated Default family')
    points=[NODE.unpack_from(raw,at+28+i*NODE.size) for i in range(4)]
    if any(not all(math.isfinite(v) for v in p[:3]) or not 0<=p[0]<=10000 or not 0<=p[1]<=1 for p in points):
        raise ValueError('Sytrus cutoff envelope is outside the calibrated four-point layout')
    return {'enabled':bool(struct.unpack_from('<i',raw,at+128)[0]),'host_scale_raw':list(scales),
            'attack_time_raw':points[1][0],'peak_level_raw':points[1][1],
            'decay_time_raw':points[2][0],'sustain_level_raw':points[2][1],
            'release_time_raw':points[3][0],'end_level_raw':points[3][1]}


def _view(profile, raw):
    matrix = []
    for mode, start in (('fm', 12), ('rm', 336)):
        for row in range(1, 7):
            for column in range(1, 7):
                value = struct.unpack_from('<i', raw, start+((row-1)*9+column-1)*4)[0]
                if value:
                    matrix.append({'mode': mode, 'row': row, 'column': column,
                                   'source': column, 'target': row, 'value_raw': value})
    outputs = [{'operator': row, 'value_raw': struct.unpack_from('<i', raw, 12+((row-1)*9+8)*4)[0]}
               for row in range(1, 7)]
    operators = []
    for operator in range(1, 7):
        base = profile['operator_base']+(operator-1)*profile['operator_stride']
        env = base+profile['volume_header']+28
        nodes = [NODE.unpack_from(raw, env+point*NODE.size) for point in range(4)]
        operators.append({'operator': operator, 'ratio': struct.unpack_from('<i', raw, base+40)[0]/10000,
            'shape_raw': struct.unpack_from('<i', raw, base+2100)[0],
            'harmonics': [{'harmonic': n+1, 'coefficient_raw': struct.unpack_from('<f', raw, base+52+n*4)[0]}
                          for n in range(32) if struct.unpack_from('<f', raw, base+52+n*4)[0]],
            'volume_envelope': {'enabled': bool(struct.unpack_from('<i', raw, env+100)[0]),
                'attack_time_raw': nodes[1][0], 'attack_level': nodes[1][1],
                'decay_time_raw': nodes[2][0], 'sustain': nodes[2][1], 'release_time_raw': nodes[3][0],
                'end_level': nodes[3][1]},
            'volume_envelope_points': [{'time_raw': node[0], 'level': node[1],
                                       'tension_raw': node[2], 'flags_raw': node[3]} for node in nodes]})
    routes=[]
    for row in range(1,10):
        source=row if row<=6 else f'filter{row-6}'
        for column,target in ((8,'fx'),(9,'out')):
            value=struct.unpack_from('<i',raw,12+((row-1)*9+column-1)*4)[0]
            if value:routes.append({'source':source,'target':target,'value_raw':value})
        if row>=7:
            for column in range(1,7):
                value=struct.unpack_from('<i',raw,12+((row-1)*9+column-1)*4)[0]
                if value:routes.append({'source':column,'target':source,'value_raw':value})
    pan=[{'source':row if row<=6 else f'filter{row-6}',
          'value_raw':struct.unpack_from('<i',raw,12+((row-1)*9+6)*4)[0]} for row in range(1,10)]
    return {'profile': profile['name'], 'state_prefix_hex': profile['prefix'].hex(),
            'expanded_state_bytes': len(raw), 'matrix': matrix, 'outputs': outputs, 'operators': operators,
            'routes':routes,'pan':pan,
            'filters':[{'filter':i,'cutoff_envelope':_cutoff_view(profile,raw,i)} for i in range(1,4)]}


def inspect_design(project: Project, channel: int) -> dict:
    profile, raw = _decode(_target(project, channel).data)
    return {'channel': channel, 'plugin': 'Sytrus', **_view(profile, raw),
            'readback_scope': 'saved_private_state', 'limitations': list(LIMITATIONS)}


def initialize(project: Project, channel: int, preset: Path | str | None = None) -> dict:
    """Load the user's local factory Default preset; no preset bytes are bundled."""
    path = Path(preset) if preset is not None else INSTALL/'Data/Patches/Plugin presets/Generators/Sytrus/Default.fst'
    preset_project = Project.read(path)
    state = [event.data for event in preset_project.events if event.id == 213]
    if len(state) != 1:
        raise ValueError('Local Sytrus Default preset must contain one state event')
    _decode(state[0])
    name = next((preset_project._text(event.data) for event in preset_project.events if event.id == 201), '')
    if name.casefold() != 'sytrus':
        raise ValueError('Initialization preset must identify Sytrus')
    project.set_channel(channel, {'plugin_preset': str(path)})
    return inspect_design(project, channel)


def apply_design(project: Project, channel: int, request: dict) -> dict:
    """Apply an atomic offline design; the caller saves and auditions its copy.

    Matrix row=target operator and column=source operator. Named source/target
    edges are equivalent; target='out' controls the source operator's direct
    output in the FM table. A native value of 256 is the calibrated full knob.
    """
    if not isinstance(request, dict) or not request or set(request)-{'init','preset','matrix','operators','routes','pan','filters'}:
        raise ValueError('Sytrus design accepts init, optional local preset, matrix, operators, shared routes/pan and filters')
    if 'init' in request and type(request['init']) is not bool:
        raise ValueError('Sytrus init must be a boolean')
    if request.get('preset') is not None and not request.get('init'):
        raise ValueError('A local initialization preset requires init=true')
    # Plan on an independent in-memory copy so malformed later changes cannot
    # leave the caller's Project partially initialized or edited.
    working = Project(project.encode())
    if request.get('init'):
        initialize(working, channel, request.get('preset'))
    event = _target(working, channel)
    profile, raw = _decode(event.data)
    before = _view(profile, raw)
    seen = set()
    matrix = request.get('matrix', [])
    if not isinstance(matrix, list):
        raise ValueError('Sytrus matrix requires an array of explicit cells or directed edges')
    for cell in matrix:
        if not isinstance(cell, dict) or set(cell)-{'mode','row','column','source','target','value_raw'}:
            raise ValueError('Matrix cells choose mode, row/column or source/target, and value_raw')
        mode = cell.get('mode', 'fm')
        if mode not in ('fm','rm'):
            raise ValueError('Matrix mode must be fm or rm')
        if {'row','column'} <= set(cell) and not ({'source','target'} & set(cell)):
            row = _integer(cell['row'],1,6,'Matrix row')
            column = 9 if cell['column'] == 'out' else _integer(cell['column'],1,6,'Matrix column')
        elif {'source','target'} <= set(cell) and not ({'row','column'} & set(cell)):
            source = _integer(cell['source'],1,6,'Matrix source')
            if cell['target'] == 'out':
                row, column = source, 9
            else:
                row, column = _integer(cell['target'],1,6,'Matrix target'), source
        else:
            raise ValueError('Choose exactly row+column or source+target for each matrix edge')
        if column == 9 and mode != 'fm':
            raise ValueError('Direct OUT is shared and is exposed only through the FM table')
        value = _integer(cell.get('value_raw'),-256,256,'Matrix value_raw')
        offset = (12 if mode=='fm' else 336)+((row-1)*9+column-1)*4
        if offset in seen:
            raise ValueError('Duplicate Sytrus matrix cell')
        seen.add(offset)
        struct.pack_into('<i', raw, offset, value)
    def source_row(source):
        if source in ('filter1','filter2','filter3'):return 6+int(source[-1])
        return _integer(source,1,6,'Route source')
    for route in request.get('routes',[]):
        if not isinstance(route,dict) or set(route)!={'source','target','value_raw'}:
            raise ValueError('A shared route requires source, target and value_raw')
        row=source_row(route['source']);target=route['target']
        if target in ('out','fx'):column=9 if target=='out' else 8
        elif target in ('filter1','filter2','filter3') and row<=6:
            column,row=row,6+int(target[-1])
        else:raise ValueError('Shared routes support OP-to-filter and OP/filter-to-FX/OUT; filter-to-filter uses Send to Next, not the matrix')
        offset=12+((row-1)*9+column-1)*4
        if offset in seen:raise ValueError('Duplicate Sytrus route/matrix cell')
        seen.add(offset);struct.pack_into('<i',raw,offset,_integer(route['value_raw'],-256,256,'Route value_raw'))
    for pan in request.get('pan',[]):
        if not isinstance(pan,dict) or set(pan)!={'source','value_raw'}:raise ValueError('Pan requires source and value_raw')
        offset=12+((source_row(pan['source'])-1)*9+6)*4
        if offset in seen:raise ValueError('Duplicate Sytrus pan cell')
        seen.add(offset);struct.pack_into('<i',raw,offset,_integer(pan['value_raw'],-256,256,'Pan value_raw'))
    used_filters=set()
    for filt in request.get('filters',[]):
        if not isinstance(filt,dict) or set(filt)!={'filter','cutoff_envelope'}:raise ValueError('Filter design requires filter and cutoff_envelope')
        number=_integer(filt['filter'],1,3,'Filter')
        if number in used_filters:raise ValueError('Duplicate Sytrus filter')
        used_filters.add(number);_cutoff_view(profile,raw,number)
        env=filt['cutoff_envelope'];fields={'attack_time_raw':(1,0),'peak_level_raw':(1,8),'decay_time_raw':(2,0),
            'sustain_level_raw':(2,8),'release_time_raw':(3,0),'end_level_raw':(3,8)}
        if not isinstance(env,dict) or not env or set(env)-set(fields)-{'enabled'}:raise ValueError('Unknown cutoff envelope field')
        enabled=env.get('enabled',True)
        if type(enabled) is not bool:raise ValueError('Cutoff envelope enabled must be boolean')
        at=_filter_header(profile,number);struct.pack_into('<i',raw,at+128,-1 if enabled else 0)
        for key,value in env.items():
            if key=='enabled':continue
            point,delta=fields[key]
            struct.pack_into('<d',raw,at+28+point*NODE.size+delta,_number(value,0,10000 if delta==0 else 1,'Cutoff '+key))
    operators = request.get('operators', [])
    if not isinstance(operators, list):
        raise ValueError('Sytrus operators requires an array')
    seen_operators = set()
    for change in operators:
        if not isinstance(change,dict) or set(change)-{'operator','ratio','shape_raw','harmonics','volume_envelope'}:
            raise ValueError('Operator accepts operator, ratio, shape_raw, harmonics and volume_envelope')
        if set(change) == {'operator'}:
            raise ValueError('Each operator requires at least one design change')
        operator = _integer(change.get('operator'),1,6,'Operator')
        if operator in seen_operators:
            raise ValueError('Duplicate Sytrus operator')
        seen_operators.add(operator)
        base = profile['operator_base']+(operator-1)*profile['operator_stride']
        if 'ratio' in change:
            ratio = _number(change['ratio'],0,64,'Operator ratio')
            if abs(ratio*10000-round(ratio*10000)) > 1e-6:
                raise ValueError('Sytrus ratio supports at most four decimal places')
            struct.pack_into('<i',raw,base+40,round(ratio*10000))
        if 'shape_raw' in change:
            struct.pack_into('<i',raw,base+2100,_integer(change['shape_raw'],0,512,'Operator shape_raw'))
        if 'harmonics' in change:
            harmonics = change['harmonics']
            if not isinstance(harmonics,list) or not harmonics:
                raise ValueError('Harmonics requires a nonempty array of harmonic/coefficient_raw')
            used = set()
            for harmonic in harmonics:
                if not isinstance(harmonic,dict) or set(harmonic)!={'harmonic','coefficient_raw'}:
                    raise ValueError('Each harmonic requires exactly harmonic and coefficient_raw')
                number = _integer(harmonic['harmonic'],1,32,'Harmonic')
                if number in used:
                    raise ValueError('Duplicate harmonic')
                used.add(number)
                coefficient = _number(harmonic['coefficient_raw'],0,1,'Harmonic coefficient_raw')
                struct.pack_into('<f',raw,base+52+(number-1)*4,coefficient)
        if 'volume_envelope' in change:
            envelope = change['volume_envelope']
            fields = {'attack_time_raw':(1,0),'attack_level':(1,8),'decay_time_raw':(2,0),
                      'sustain':(2,8),'release_time_raw':(3,0),'end_level':(3,8)}
            if not isinstance(envelope,dict) or not envelope or set(envelope)-set(fields)-{'enabled'}:
                raise ValueError('Volume envelope accepts enabled, attack_time_raw/level, decay_time_raw, sustain, release_time_raw and end_level')
            enabled = envelope.get('enabled', True)
            if type(enabled) is not bool:
                raise ValueError('Volume envelope enabled must be a boolean')
            struct.pack_into('<i',raw,base+profile['volume_header']+128,-1 if enabled else 0)
            for name,value in envelope.items():
                if name == 'enabled':
                    continue
                point, delta = fields[name]
                value = _number(value,0,10000 if delta==0 else 1,'Volume envelope '+name)
                struct.pack_into('<d',raw,base+profile['volume_header']+28+point*NODE.size+delta,value)
    new_blob = event.data[:4]+zlib.compress(bytes(raw))
    _decode(new_blob)
    event.data = new_blob
    after = _view(profile,raw)
    project.events = working.events
    project._channel_cache = None
    return {'channel':channel, 'plugin':'Sytrus', 'initialized':bool(request.get('init')),
            'before':before, 'after':after, 'live_applied':False,
            'readback_scope':'saved_private_state', 'limitations':list(LIMITATIONS)}


# Concise import aliases for adapter callers.
inspect = inspect_design
apply = apply_design
