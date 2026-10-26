"""Three practical regression checks; native FL exports are checked separately."""
from pathlib import Path
import json
import struct
import wave

from click.testing import CliRunner

from flstudio_cli.cli import app
from flstudio_cli.flp import Event, Project, create_project


def fixture(tmp_path):
    template = Path('C:/Program Files/Image-Line/FL Studio 2026/Data/Templates/Minimal/Basic/Basic.flp')
    sample = tmp_path / 'sample.wav'
    with wave.open(str(sample), 'wb') as file:
        file.setparams((1, 2, 44100, 0, 'NONE', ''))
        file.writeframes(bytes(1000))
    note = {'key': 60, 'start_tick': 0, 'length_tick': 24, 'velocity': 100}
    spec = {'tempo_bpm': 137, 'channels': [
        {'name': '鼓', 'sample_path': str(sample)}, {'name': 'Bass', 'sample_path': str(sample)}],
        'patterns': [{'number': 7, 'name': '节奏', 'scores': [
            {'channel_index': 0, 'notes': [note, dict(note, start_tick=192)]},
            {'channel_index': 1, 'notes': [dict(note, key=48)]}]}],
        'playlist': [{'pattern_number': 7, 'track': 3, 'start_tick': 384, 'length_tick': 768}]}
    return template, spec


def test_project_roundtrip_and_exact_score_edit(tmp_path):
    template, spec = fixture(tmp_path)
    original = template.read_bytes()
    assert Project(original).encode() == original, 'Untouched vendor events must round-trip byte-for-byte'
    limiter_template = template.parent.parent / 'Basic with limiter/Basic with limiter.flp'
    assert Project.read(limiter_template).mixer()[0]['plugins'][0]['name'] == 'Emphasizer', 'Factory Master FX must stay on Master'
    project = create_project(spec, template)
    output = project.save(tmp_path / 'built.flp')
    saved = output.read_bytes()
    doc = Project.read(output)
    assert doc.tempo == 137 and [c['name'] for c in doc.channels()] == ['鼓', 'Bass']
    assert next(e.data for e in doc.events if e.id == 9) == b'\1', 'New arrangements must open in Song mode'
    assert [n['channel_index'] for n in doc.patterns()[7]['notes']] == [0, 1, 0]
    assert doc.playlist()[0]['track'] == 3
    other = [n for n in doc.patterns()[7]['notes'] if n['channel_index'] == 1]
    doc.replace_notes(7, 0, [{'key': 39, 'start_tick': 96, 'length_tick': 48, 'velocity': 83}])
    doc.set_channel(0, {'pan_raw': -2000, 'mixer_track': 1})
    doc.set_mixer(1, {'volume_raw': 10000})
    changed = Project.read(doc.save(tmp_path / 'edited.flp'))
    assert [n['channel_index'] for n in changed.patterns()[7]['notes']] == [1, 0], 'FL requires chronological records across channels'
    assert [n for n in changed.patterns()[7]['notes'] if n['channel_index'] == 1] == other
    assert [n['key'] for n in changed.patterns()[7]['notes'] if n['channel_index'] == 0] == [39]
    assert changed.channels()[0]['pan_raw'] == -2000
    assert changed.mixer()[1]['volume_raw'] == 10000
    assert output.read_bytes() == saved and template.read_bytes() == original
    native = Project.read(limiter_template)
    native.replace_notes(3, 0, [dict(spec['patterns'][0]['scores'][0]['notes'][0], start_tick=384)])
    native.set_playlist([{'pattern_number': 3, 'track': 1, 'start_tick': 0, 'length_tick': 768}])
    native_copy = Project.read(native.save(tmp_path / 'native-edited.flp'))
    assert len(next(e.data for e in native_copy.events if e.id == 233)) == 88, 'FL26 stores fresh Playlist items in 88-byte records'
    assert native_copy.playlist()[0]['length_tick'] == 768
    previous = native_copy._effect_state(0, 9)[1].data
    native_copy.set_plugin_parameter(0, 9, 'Emphasis', .25)
    param_copy = Project.read(native_copy.save(tmp_path / 'one-param.flp'))
    assert param_copy.plugin_parameters(0, 9)['params'][0]['v'] == .25
    actual = param_copy._effect_state(0, 9)[1].data
    assert actual[:8] == previous[:8] and actual[12:] == previous[12:]
    probe = create_project(spec, template)
    probe.load_effect(0, 0, native_copy.effect_events(0, 9))
    probe.set_plugin_parameter(0, 0, 'Emphasis', .4)
    assert native_copy._effect_state(0, 9)[1].data == actual, 'Verification must copy rather than mutate the source effect'


def test_cli_build_preview_and_source_preservation(tmp_path):
    template, spec = fixture(tmp_path)
    request, output = tmp_path / 'request.json', tmp_path / 'song.flp'
    request.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
    runner = CliRunner()
    args = ['project', 'build', '--request', str(request), '--template', str(template), '--output', str(output)]
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    preview = runner.invoke(app, args + ['--dry-run'])
    assert preview.exit_code == 0 and json.loads(preview.output)['status'] == 'planned'
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    built = runner.invoke(app, args)
    assert built.exit_code == 0 and json.loads(built.output)['data']['file_note_count'] == 3
    stored = output.read_bytes()
    duplicate = runner.invoke(app, args)
    assert duplicate.exit_code != 0 and output.read_bytes() == stored
    for command in ([ 'set-tempo', '--bpm', '123'],
                    ['set-mixer-pan', '--track', '1', '--value', '.25'],
                    ['set-plugin-param', '--track', '0', '--slot', '9', '--param', 'Emphasis', '--value', '.25']):
        preview = runner.invoke(app, ['live', '--bridge-port', '1', *command, '--dry-run'])
        assert preview.exit_code == 0 and json.loads(preview.output)['data']['bridge_contacted'] is False
    assert output.read_bytes() == stored
    verify_output = tmp_path / 'parameter-check'
    profile = template.parent.parent / 'Basic with limiter/Basic with limiter.flp'
    preview = runner.invoke(app, ['plugin', 'verify', '--project', str(profile), '--track', '0',
        '--slot', '9', '--param', 'Emphasis', '--value', '.25', '--output-dir', str(verify_output), '--dry-run'])
    assert preview.exit_code == 0 and json.loads(preview.output)['status'] == 'planned' and not verify_output.exists()
    live_request = tmp_path / 'stop.json'
    live_request.write_text(json.dumps({'command': 'stop', 'params': {},
        'readback': {'command': 'get_play_state', 'params': {}, 'expect': {'playing': False}}}))
    preview = runner.invoke(app, ['live', '--bridge-port', '1', 'apply', '--request', str(live_request), '--dry-run'])
    assert preview.exit_code == 0 and json.loads(preview.output)['data']['bridge_contacted'] is False


def test_unknown_events_and_json_numbers_are_not_silently_corrupted(tmp_path):
    from flstudio_cli.json_output import JsonValueError, canonical_json, decode_json
    template, _ = fixture(tmp_path)
    doc = Project.read(template)
    doc.events.insert(2, Event(254, bytes(range(256))))
    copy = Project(doc.encode())
    assert next(e.data for e in copy.events if e.id == 254) == bytes(range(256))
    assert json.loads(canonical_json({'name': '湿', 'value': -0.0})) == {'name': '湿', 'value': 0}
    for bad in ('{"value":NaN}', '{"\ud800":1,"\ud800":2}'):
        try:
            decode_json(bad)
        except JsonValueError:
            pass
        else:
            raise AssertionError('Invalid numeric/Unicode input was accepted')
