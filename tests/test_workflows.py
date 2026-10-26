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
    project = create_project(spec, template)
    output = project.save(tmp_path / 'built.flp')
    saved = output.read_bytes()
    doc = Project.read(output)
    assert doc.tempo == 137 and [c['name'] for c in doc.channels()] == ['鼓', 'Bass']
    assert next(e.data for e in doc.events if e.id == 9) == b'\1', 'New arrangements must open in Song mode'
    assert [n['channel_index'] for n in doc.patterns()[7]['notes']] == [0, 0, 1]
    assert doc.playlist()[0]['track'] == 3
    other = [n for n in doc.patterns()[7]['notes'] if n['channel_index'] == 1]
    doc.replace_notes(7, 0, [{'key': 39, 'start_tick': 96, 'length_tick': 48, 'velocity': 83}])
    doc.set_channel(0, {'pan_raw': -2000, 'mixer_track': 1})
    doc.set_mixer(1, {'volume_raw': 10000})
    changed = Project.read(doc.save(tmp_path / 'edited.flp'))
    assert [n['channel_index'] for n in changed.patterns()[7]['notes']] == [0, 1], 'FL requires channel-ordered score records'
    assert [n for n in changed.patterns()[7]['notes'] if n['channel_index'] == 1] == other
    assert [n['key'] for n in changed.patterns()[7]['notes'] if n['channel_index'] == 0] == [39]
    assert changed.channels()[0]['pan_raw'] == -2000
    assert changed.mixer()[1]['volume_raw'] == 10000
    assert output.read_bytes() == saved and template.read_bytes() == original


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
