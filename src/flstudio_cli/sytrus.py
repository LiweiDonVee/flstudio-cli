"""Sytrus host controls, without rewriting its compressed private preset state."""
from __future__ import annotations

from .mixing import initial_values, set_initial


# Native host parameter IDs and integer units, not normalized live values.
# The preset blob remains byte-for-byte intact. FL applies these controls
# when opening/starting the saved project.
def catalog() -> list[dict]:
    result = []
    def add(param, index, low, high, unit='native_raw'):
        result.append({'param': param, 'index': index, 'minimum': low, 'maximum': high, 'unit': unit})
    for name, index, low, high in (
        ('master_level', 0, 0, 160), ('master_lfo_level', 1, -128, 128), ('master_pitch', 2, -24, 24),
        ('volume_attack', 3, 0, 256), ('volume_decay', 4, 0, 256), ('volume_sustain', 5, -128, 128),
        ('volume_release', 6, 0, 256), ('filter_attack', 7, 0, 256), ('filter_decay', 8, 0, 256),
        ('filter_sustain', 9, -128, 128), ('filter_release', 10, 0, 256), ('unison_order', 11, 1, 9),
        ('unison_pan', 12, 0, 128), ('unison_volume', 13, 16, 128), ('unison_pitch', 14, 0, 256),
        ('unison_sub', 15, 0, 96), ('unison_phase', 16, 0, 128), ('unison_envelope', 17, 0, 192),
        ('mod_x', 18, 0, 512), ('mod_y', 19, 0, 512), ('portamento', 596, 0, 1)):
        add(name, index, low, high, 'semitones' if name == 'master_pitch' else 'native_raw')
    for operator in range(1, 7):
        base = 20 + (operator - 1) * 51
        add(f'op{operator}.phase', base, 0, 256)
        add(f'op{operator}.volume', base + 1, -256, 256)
        add(f'op{operator}.pitch_envelope', base + 2, 0, 4800)
        for name, offset, low, high in (('attack', 11, 0, 256), ('decay', 12, 0, 256),
                                       ('sustain', 13, -128, 128), ('release', 14, 0, 256)):
            add(f'op{operator}.volume_{name}', base + offset, low, high)
    for filt in range(1, 4):
        base = 327 + (filt - 1) * 74
        add(f'filter{filt}.cutoff_envelope', base, 0, 256)
        add(f'filter{filt}.cutoff', base + 1, 0, 256)
        add(f'filter{filt}.resonance', base + 2, 0, 256)
    for name, index, low, high in (
        ('chorus.order', 548, 0, 9), ('chorus.depth', 549, 0, 1024), ('chorus.speed', 550, 0, 1024),
        ('chorus.delay', 551, 0, 128), ('chorus.spread', 552, 0, 128),
        ('chorus.cross', 553, -128, 128), ('chorus.volume', 554, -128, 128)):
        add(name, index, low, high)
    for delay in range(1, 4):
        base = 556 + (delay - 1) * 5
        for name, offset, low, high in (('feedback', 0, 0, 127), ('time', 1, 0, 384),
                                       ('stereo_time', 2, -512, 512), ('volume', 3, -128, 128),
                                       ('feedback_mode', 4, 0, 2)):
            add(f'delay{delay}.{name}', base + offset, low, high)
    for band in range(1, 4):
        add(f'eq{band}.level', 586 + band, -1800, 1800)
        add(f'eq{band}.frequency', 589 + band, 0, 65536)
        add(f'eq{band}.width', 592 + band, 0, 65536)
    return result


def _target(project, channel):
    channels = project.channels()
    if type(channel) is not int or not 0 <= channel < len(channels):
        raise ValueError('Sytrus channel must be an existing global saved channel index')
    info = channels[channel]
    if info['plugin'].casefold() != 'sytrus':
        raise ValueError(f'Channel {channel} is {info["plugin"]}, not Sytrus')
    start, end = project.channel_spans()[channel]
    state = next((e.data for e in project.events[start:end] if e.id == 213), None)
    if not state or len(state) < 4:
        raise ValueError('Sytrus preset state is missing')
    # Host controls belong to the installed Sytrus, not the preset's old
    # serialization version. FL upgrades its own factory presets on loading.
    return {**info, 'state_prefix_hex': state[:4].hex()}


def parameters(project, channel: int, search='') -> dict:
    info = _target(project, channel)
    values = initial_values(project)
    base = (info['iid'] << 16) | 0x8000
    params = [{**entry, 'value_raw': values.get(base + entry['index']),
               'value_source': 'saved_host_override' if base + entry['index'] in values else 'opaque_preset'}
              for entry in catalog() if search.casefold() in entry['param'].casefold()]
    return {'channel': channel, 'channel_iid': info['iid'], 'plugin': 'Sytrus', 'state_prefix_hex': info['state_prefix_hex'],
            'params': params, 'units': 'Integer native host controls; live API uses normalized 0..1',
            'limitations': ['Null means the value is inside the unchanged preset, not zero',
                            'FM/RM matrix, custom harmonics and envelope point editing remain preset/GUI operations']}


def set_parameters(project, channel: int, changes: list[dict]) -> list[dict]:
    info = _target(project, channel)
    if not isinstance(changes, list) or not changes:
        raise ValueError('Sytrus params must be a nonempty array of {param, value_raw}')
    available = catalog()
    planned, seen = [], set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'param', 'value_raw'}:
            raise ValueError('Each Sytrus change requires exactly param and value_raw')
        param, value = change['param'], change['value_raw']
        matches = [p for p in available if p['param'] == param or type(param) is int and p['index'] == param]
        if len(matches) != 1:
            raise ValueError(f'Unknown Sytrus host control {param!r}; see sytrus params')
        target = matches[0]
        if type(value) is not int or not target['minimum'] <= value <= target['maximum']:
            raise ValueError(f'{target["param"]} value_raw must be an integer {target["minimum"]}..{target["maximum"]}')
        if target['index'] in seen:
            raise ValueError('Duplicate Sytrus parameter in one request')
        seen.add(target['index'])
        planned.append({**target, 'value_raw': value})
    base = (info['iid'] << 16) | 0x8000
    for change in planned:
        set_initial(project, base + change['index'], change['value_raw'], event_id=216)
    return planned


def register(app, emit, json_option):
    from pathlib import Path
    import click
    from .contracts import Result
    from .flp import Project
    from .json_output import decode_json

    @app.group('sytrus')
    @json_option
    def group():
        """Discover Sytrus presets and edit saved native host controls."""

    @group.command('params')
    @click.option('--project', 'source', required=True, type=click.Path(path_type=Path))
    @click.option('--channel', required=True, type=click.IntRange(0, 4095))
    @click.option('--search', default='')
    @json_option
    def params(source, channel, search):
        emit(Result(command='sytrus params', status='verified', verified_scopes=['saved_host_overrides'],
                    data=parameters(Project.read(source), channel, search)))

    @group.command('edit')
    @click.option('--project', 'source', required=True, type=click.Path(path_type=Path))
    @click.option('--channel', required=True, type=click.IntRange(0, 4095))
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def edit(source, channel, request, output, dry_run):
        doc = Project.read(source)
        changed = set_parameters(doc, channel, decode_json(request.read_text(encoding='utf-8-sig')))
        data = {'channel': channel, 'changes': changed, 'output': str(output.resolve()), 'live_applied': False}
        if dry_run:
            data.update(applied_count=None, file_effects=[])
            emit(Result(command='sytrus edit', status='planned', data=data))
            return
        doc.save(output)
        saved = Project.read(output)
        if parameters(saved, channel) != parameters(doc, channel):
            raise ValueError('Sytrus saved-host override readback differs')
        emit(Result(command='sytrus edit', status='artifact_ready', verified_scopes=['saved_host_overrides'], data=data))
