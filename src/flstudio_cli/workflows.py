"""File-based composing and rendering commands share explicit saved targets."""
from __future__ import annotations

from pathlib import Path
import hashlib

import click
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import NoteInput, Result
from .flp import Project, create_project
from .json_output import decode_json

DEFAULT_INSTALL = Path('C:/Program Files/Image-Line/FL Studio 2026')


class Spec(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Channel(Spec):
    name: str = Field(min_length=1)
    sample_path: str | None = None
    plugin_preset: str | None = None
    mixer_track: int = Field(default=0, ge=0, le=125)
    volume_raw: int = Field(default=10000, ge=0, le=12800)
    pan_raw: int = Field(default=0, ge=-6400, le=6400)

    @model_validator(mode='after')
    def source(self):
        if bool(self.sample_path) == bool(self.plugin_preset):
            raise ValueError('Specify exactly one sample_path or plugin_preset')
        return self


class Score(Spec):
    channel_index: int = Field(ge=0)
    notes: list[NoteInput]


class Pattern(Spec):
    number: int = Field(ge=1, le=999)
    name: str = 'Pattern'
    scores: list[Score]


class Clip(Spec):
    pattern_number: int = Field(ge=1, le=999)
    track: int = Field(ge=1, le=500)
    start_tick: int = Field(ge=0)
    length_tick: int = Field(gt=0)


class Composition(Spec):
    tempo_bpm: float | int = Field(default=130, ge=10, le=522)
    channels: list[Channel] = Field(min_length=1, max_length=128)
    patterns: list[Pattern] = Field(min_length=1)
    playlist: list[Clip] = Field(min_length=1)

    @model_validator(mode='after')
    def references(self):
        numbers = [pattern.number for pattern in self.patterns]
        if len(numbers) != len(set(numbers)):
            raise ValueError('Pattern numbers must be unique')
        for pattern in self.patterns:
            indices = [score.channel_index for score in pattern.scores]
            if len(indices) != len(set(indices)) or any(index >= len(self.channels) for index in indices):
                raise ValueError('Scores must reference unique, existing channels')
        if any(clip.pattern_number not in numbers for clip in self.playlist):
            raise ValueError('Playlist references an undefined pattern')
        return self


def read_json(path):
    return decode_json(Path(path).read_text(encoding='utf-8-sig'))


def register(app, emit, json_option):
    @app.group()
    @json_option
    def project():
        """Inspect, create, and edit explicit saved FL projects."""

    @project.command('inspect')
    @click.option('--input', 'source', required=True, type=click.Path(path_type=Path))
    @click.option('--summary', is_flag=True, help='Omit individual note records.')
    @json_option
    def inspect(source, summary):
        doc = Project.read(source)
        emit(Result(command='project inspect', status='verified',
                    verified_scopes=['saved_channels', 'saved_notes', 'saved_playlist', 'saved_mixer'],
                    data=doc.inspect(not summary)))

    @project.command('build')
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--template', type=click.Path(path_type=Path), default=None)
    @click.option('--dry-run', is_flag=True)
    @json_option
    def build(request, output, template, dry_run):
        """Build a new Sampler composition, retaining the real FL template data."""
        spec = Composition.model_validate(read_json(request))
        source = template or DEFAULT_INSTALL / 'Data/Templates/Minimal/Basic/Basic.flp'
        doc = create_project(spec.model_dump(), source)
        data = doc.inspect()
        data.update(output=str(output.resolve()), requested_count=sum(len(s.notes) for p in spec.patterns for s in p.scores))
        if dry_run:
            data.update(applied_count=None, file_effects=[])
            emit(Result(command='project build', status='planned', data=data))
            return
        doc.save(output)
        after = Project.read(output)
        if after.patterns() != doc.patterns() or after.channels() != doc.channels() or after.playlist() != doc.playlist():
            raise ValueError('Saved project readback differs from the requested composition')
        data.update(file_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                    file_note_count=sum(len(p['notes']) for p in after.patterns().values()), live_applied=False)
        emit(Result(command='project build', status='artifact_ready',
                    verified_scopes=['saved_notes', 'saved_channels', 'saved_playlist'], data=data))

    @project.command('edit')
    @click.option('--input', 'source', required=True, type=click.Path(path_type=Path))
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def edit(source, request, output, dry_run):
        """Apply explicit note/channel/playlist/mixer changes to a new FLP copy."""
        changes = read_json(request)
        if not isinstance(changes, dict) or set(changes) - {'tempo_bpm', 'channels', 'scores', 'patterns', 'playlist', 'mixer', 'effects', 'plugin_params'}:
            raise ValueError('Unknown project edit section')
        doc = Project.read(source)
        if 'tempo_bpm' in changes:
            doc.set_tempo(changes['tempo_bpm'])
        for channel in changes.get('channels', []):
            doc.set_channel(channel['index'], {k: v for k, v in channel.items() if k != 'index'})
        for score in changes.get('scores', []):
            if score.get('mode', 'replace') not in ('append', 'replace'):
                raise ValueError('Score mode must be replace or append')
            doc.replace_notes(score['pattern_number'], score['channel_index'], score['notes'], score.get('mode') == 'append')
        for pattern in changes.get('patterns', []):
            doc.name_pattern(pattern['number'], pattern['name'])
        if 'playlist' in changes:
            doc.set_playlist([Clip.model_validate(c).model_dump() for c in changes['playlist']])
        for mixer in changes.get('mixer', []):
            doc.set_mixer(mixer['track'], {k: v for k, v in mixer.items() if k != 'track'})
        for effect in changes.get('effects', []):
            doc.load_effect(effect['track'], effect['slot'], effect['preset'])
        for parameter in changes.get('plugin_params', []):
            doc.set_plugin_parameter(parameter['track'], parameter['slot'], parameter['param'], parameter['value'])
        data = {'source': str(source.resolve()), 'output': str(output.resolve()),
                'after': doc.inspect(), 'live_applied': False}
        if dry_run:
            data.update(applied_count=None, file_effects=[])
            emit(Result(command='project edit', status='planned', data=data))
            return
        doc.save(output)
        readback = Project.read(output)
        if readback.inspect()['patterns'] != data['after']['patterns']:
            raise ValueError('Note readback mismatch after saving')
        if readback.channels() != doc.channels() or readback.mixer() != doc.mixer():
            raise ValueError('Channel or mixer readback mismatch after saving')
        emit(Result(command='project edit', status='artifact_ready',
                    verified_scopes=['saved_notes', 'saved_channels', 'saved_playlist', 'saved_mixer'] +
                    (['saved_plugin_param'] if changes.get('plugin_params') else []), data=data))

    @app.group('plugin')
    @json_option
    def plugin_group():
        """Read supported saved effect parameters without touching live FL."""

    @plugin_group.command('params')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @click.option('--track', required=True, type=click.IntRange(0, 125))
    @click.option('--slot', required=True, type=click.IntRange(0, 9))
    @json_option
    def saved_params(project, track, slot):
        doc = Project.read(project)
        emit(Result(command='plugin params', status='verified', verified_scopes=['saved_plugin_param'],
                    data=doc.plugin_parameters(track, slot)))

    @plugin_group.command('verify')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @click.option('--track', required=True, type=click.IntRange(0, 125))
    @click.option('--slot', required=True, type=click.IntRange(0, 9))
    @click.option('--param', required=True)
    @click.option('--value', required=True, type=click.FloatRange(0, 1))
    @click.option('--output-dir', required=True, type=click.Path(path_type=Path))
    @click.option('--fl-install', default=DEFAULT_INSTALL, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def verify_param(project, track, slot, param, value, output_dir, fl_install, dry_run):
        """Save a precise parameter edit and verify its audio response in FL."""
        from .plugin_verify import verify
        data = verify(project, track, slot, param, value, output_dir, fl_install, dry_run)
        emit(Result(command='plugin verify', status=data['status'], reason_code=data.get('reason'),
                    verified_scopes=['saved_plugin_param', 'fl_engine_export', 'plugin_audio_response']
                    if data['status'] == 'verified' else [], data=data))
        if data['status'] in ('failed', 'unknown'):
            raise click.exceptions.Exit(5)

    @app.group('render')
    @json_option
    def render_group():
        """Render with the actual FL engine in an isolated Windows desktop."""

    @render_group.command('wav')
    @click.option('--project', 'source', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--fl-install', default=DEFAULT_INSTALL, type=click.Path(path_type=Path))
    @click.option('--timeout', default=120.0, type=click.FloatRange(min=1, max=1800))
    @click.option('--dry-run', is_flag=True)
    @click.option('--allow-silence', is_flag=True, help='Accept intentionally silent output, retaining duration checks.')
    @json_option
    def render_wav(source, output, fl_install, timeout, dry_run, allow_silence):
        doc = Project.read(source)
        if dry_run:
            emit(Result(command='render wav', status='planned', data={'source': str(source.resolve()),
                        'output': str(output.resolve()), 'backend': 'fl_native_batch', 'file_effects': [], 'applied_count': None}))
            return
        from .native import render
        data = render(source, output, fl_install, timeout, allow_silence)
        emit(Result(command='render wav', status=data['status'], reason_code=data.get('reason'),
                    verified_scopes=['fl_engine_export', 'pcm_audio'] if data['status'] == 'verified' else [], data=data))
        if data['status'] != 'verified':
            raise click.exceptions.Exit(5)

    @app.group('audio')
    @json_option
    def audio_group():
        """Read rendered PCM audio metadata and levels."""

    @audio_group.command('inspect')
    @click.option('--input', 'source', required=True, type=click.Path(path_type=Path))
    @json_option
    def inspect_audio(source):
        from .native import read_audio
        metadata, _ = read_audio(source)
        emit(Result(command='audio inspect', status='verified', verified_scopes=['pcm_audio'], data=metadata))
