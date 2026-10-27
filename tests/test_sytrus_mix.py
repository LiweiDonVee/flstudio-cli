"""One saved-project workflow covers synth targeting and complete FX-chain edits."""
from pathlib import Path
import hashlib
import json
import struct

from click.testing import CliRunner

from flstudio_cli.cli import app
from flstudio_cli.flp import Event, Project, create_project


def test_sytrus_to_bus_fx_chain_roundtrip(tmp_path):
    install = Path('C:/Program Files/Image-Line/FL Studio 2026')
    presets = install / 'Data/Patches/Plugin presets'
    spec = {'tempo_bpm': 120, 'channels': [
        {'name': 'Sytrus', 'plugin_preset': str(presets / 'Generators/Sytrus/Default.fst'), 'mixer_track': 1}],
        'patterns': [{'number': 1, 'scores': [{'channel_index': 0, 'notes': [
            {'key': 48, 'start_tick': 0, 'length_tick': 192, 'velocity': 100}]}]}],
        'playlist': [{'pattern_number': 1, 'track': 1, 'start_tick': 0, 'length_tick': 384}]}
    doc = create_project(spec, install / 'Data/Templates/Minimal/Basic/Basic.flp')
    doc.load_effect(1, 0, presets / 'Effects/Fruity Reeverb 2/Default.fst')
    from flstudio_cli.plugin_profiles import apply_parameters
    apply_parameters(doc, [{'track': 1, 'slot': 0, 'param': 'wet', 'value_raw': 64}])
    # Start controls take precedence over FX initial values, independent of
    # their physical order in a saved file.
    at = next(i for i, e in enumerate(doc.events) if e.id == 64)
    doc.events.insert(at, Event(216, struct.pack('<IIi', 0, 0x7040800c, 32)))
    source = doc.save(tmp_path / 'source.flp')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    reverb_state = doc._effect_state(1, 0)[1].data
    changes = {'sytrus': [{'channel': 0, 'params': [{'param': 'master_pitch', 'value_raw': 12}]}],
        'mixer': [{'track': 1, 'routes': [6], 'sends': [{'to': 6, 'level': 0.35}]},
                  {'track': 6, 'name': 'SYNTH BUS', 'routes': [0]}],
        'fx_chains': [{'track': 1, 'slots': []}, {'track': 6, 'slots': [
            {'slot': 2, 'copy_from': {'track': 1, 'slot': 0}, 'enabled': False, 'wet': 0.4}]}]}
    request, output = tmp_path / 'edit.json', tmp_path / 'mixed.flp'
    request.write_text(json.dumps(changes), encoding='utf-8')
    runner = CliRunner()
    args = ['project', 'edit', '--input', str(source), '--request', str(request), '--output', str(output)]
    preview = runner.invoke(app, args + ['--dry-run'])
    assert preview.exit_code == 0, preview.output
    assert not output.exists()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    saved = Project.read(output)
    assert saved._effect_state(6, 2)[1].data == reverb_state
    assert next(p for p in saved.plugin_parameters(6, 2)['params'] if p['param'] == 'wet')['value_raw'] == 32
    assert saved.mixer()[1]['plugins'] == []
    fx = saved.mixer()[6]['plugins'][0]
    assert fx['slot'] == 2 and fx['enabled'] is False and fx['wet'] == 0.4
    assert saved.mixer()[1]['sends'] == [{'to': 6, 'level': 0.35}]
    from flstudio_cli.mixing import initial_values
    assert initial_values(saved)[0x70402006] == 4480, 'FL25/26 stores expanded mixer sends outside the legacy general-control range'
    from flstudio_cli.sytrus import parameters
    assert next(p for p in parameters(saved, 0)['params'] if p['param'] == 'master_pitch')['value_raw'] == 12
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    # Repeating route selection must retain a deliberately reduced send.
    saved.set_mixer(1, {'routes': [6]})
    assert saved.mixer()[1]['sends'] == [{'to': 6, 'level': 0.35}]
    saved.set_channel(0, {'plugin_preset': str(presets / 'Generators/Sytrus/Default.fst')})
    assert next(p for p in parameters(saved, 0)['params'] if p['param'] == 'master_pitch')['value_raw'] is None
