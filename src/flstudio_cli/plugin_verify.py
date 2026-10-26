"""Verify supported parameter state with FL's engine and controlled input."""
from __future__ import annotations

import array
import hashlib
import math
from pathlib import Path
import wave

from .flp import Project, create_project
from .json_output import canonical_json
from .native import read_audio, render


def verify(source: Path, track: int, slot: int, param: str, value: float,
           output: Path, install: Path, dry_run=False) -> dict:
    original = Project.read(source)
    requested = Project(original.source)
    change = requested.set_plugin_parameter(track, slot, param, value)
    expected_state = requested._effect_state(track, slot)[1].data
    before_value = change['before']['params'][0]['v']
    after_value = change['after']['params'][0]['v']
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Choose a new output directory with an existing parent')
    if dry_run:
        return {'status': 'planned', 'target': change, 'output': str(output.resolve()),
                'applied_count': None, 'file_effects': [], 'live_applied': False}
    output.mkdir()
    artifact = requested.save(output / 'project.flp')
    saved = Project.read(artifact)
    if saved._effect_state(track, slot)[1].data != expected_state:
        raise ValueError('Saved effect state differs from the requested state')

    # Emphasizer's clipping response is insensitive to a quiet drum hit.
    # Keep both probes identical except for the target parameter, and drive
    # the actual copied effect with a deterministic, broadband input.
    sample = output / 'probe-input.wav'
    rate = 44100
    pcm = array.array('h', (round(30000 * sum(amplitude * math.sin(2 * math.pi * frequency * n / rate)
                            for amplitude, frequency in ((.5, 180), (.3, 2100), (.2, 7700))))
                           for n in range(rate)))
    with wave.open(str(sample), 'wb') as audio:
        audio.setparams((1, 2, rate, 0, 'NONE', ''))
        audio.writeframes(pcm.tobytes())
    spec = {'tempo_bpm': 130, 'channels': [{'name': f'Probe {i + 1}', 'sample_path': str(sample.resolve()),
            'volume_raw': 12800, 'pan_raw': 0, 'mixer_track': 0} for i in range(4)],
            'patterns': [{'number': 1, 'name': 'Parameter verification', 'scores': [{'channel_index': i,
                'notes': [{'key': 60, 'start_tick': 0, 'length_tick': 384, 'velocity': 127}]} for i in range(4)]}],
            'playlist': [{'pattern_number': 1, 'track': 1, 'start_tick': 0, 'length_tick': 384}]}
    base_probe = create_project(spec, install / 'Data/Templates/Minimal/Basic/Basic.flp')
    base_probe.load_effect(0, 0, original.effect_events(track, slot))
    changed_probe = Project(base_probe.encode())
    changed_probe.set_plugin_parameter(0, 0, param, after_value)
    signals, renders = [], []
    for label, probe in (('before', base_probe), ('after', changed_probe)):
        path = probe.save(output / f'probe-{label}.flp')
        result = render(path, output / f'probe-{label}.wav', install)
        renders.append(result)
        if result['status'] != 'verified':
            data = {'status': 'failed', 'reason': 'parameter_probe_render_failed', 'renders': renders}
            (output / 'verification.json').write_text(canonical_json(data), encoding='utf-8')
            return data
        _, signal = read_audio(output / f'probe-{label}.wav')
        signals.append(signal)
    if len(signals[0]) != len(signals[1]):
        raise ValueError('Parameter probes rendered different durations')
    differences = [a - b for a, b in zip(*signals)]
    difference_rms = math.sqrt(sum(x*x for x in differences) / max(1, len(differences)))
    changed = difference_rms > .001  # Well above 16-bit rounding or dither.
    source_unchanged = hashlib.sha256(source.read_bytes()).hexdigest() == hashlib.sha256(original.source).hexdigest()
    confirmed = changed and before_value != after_value and source_unchanged
    data = {'status': 'verified' if confirmed else 'unknown',
            'reason': None if confirmed else 'parameter_audio_response_inconclusive',
            'project': str(artifact), 'target': change, 'live_applied': False,
            'verification_context': 'isolated FL engine, copied effect, controlled input',
            'difference_rms': difference_rms, 'maximum_difference': max(map(abs, differences), default=0),
            'input_unchanged': source_unchanged, 'renders': renders,
            'scope': 'Saved parameter state and engine audio response; not the open editor state'}
    (output / 'verification.json').write_text(canonical_json(data), encoding='utf-8')
    return data
