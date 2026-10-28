"""File-based composing and rendering commands share explicit saved targets."""
from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Literal

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
    kind: Literal['sampler', 'audio', 'generator'] | None = None
    mixer_track: int = Field(default=0, ge=0, le=65535)
    volume_raw: int = Field(default=10000, ge=0, le=12800)
    pan_raw: int = Field(default=0, ge=-6400, le=6400)

    @model_validator(mode='after')
    def source(self):
        if bool(self.sample_path) == bool(self.plugin_preset):
            raise ValueError('Specify exactly one sample_path or plugin_preset')
        if ((self.sample_path and self.kind == 'generator') or
                (self.plugin_preset and self.kind not in (None, 'generator'))):
            raise ValueError('Channel kind must agree with its sample or generator preset')
        return self


class Score(Spec):
    channel_index: int = Field(ge=0)
    notes: list[NoteInput]


class Pattern(Spec):
    number: int = Field(ge=1, le=999)
    name: str = 'Pattern'
    scores: list[Score]


class Clip(Spec):
    pattern_number: int | None = Field(default=None, ge=1, le=999)
    channel_index: int | None = Field(default=None, ge=0)
    track: int = Field(ge=1, le=500)
    start_tick: int = Field(ge=0)
    length_tick: int = Field(gt=0)
    group: int = Field(default=0, ge=0, le=65535)
    source_start_tick: int | None = Field(default=None, ge=0)
    source_start_ms: float | int | None = Field(default=None, ge=0)
    source_end_ms: float | int | None = Field(default=None, gt=0)
    gain: float | int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def kind(self):
        if (self.pattern_number is None) == (self.channel_index is None):
            raise ValueError('Choose exactly one pattern_number or channel_index')
        if (self.source_start_ms is None) != (self.source_end_ms is None):
            raise ValueError('Audio cuts require both source_start_ms and source_end_ms')
        if self.source_start_tick is not None and self.source_start_ms is not None:
            raise ValueError('Choose a source window in ticks or milliseconds')
        return self


class Composition(Spec):
    tempo_bpm: float | int = Field(default=130, ge=10, le=999)
    channels: list[Channel] = Field(min_length=1, max_length=4096)
    patterns: list[Pattern] = Field(default_factory=list)
    playlist: list[Clip] = Field(min_length=1)
    mixer: list[dict] = Field(default_factory=list)
    effects: list[dict] = Field(default_factory=list)
    fx_chains: list[dict] = Field(default_factory=list)
    sytrus: list[dict] = Field(default_factory=list)
    plugin_params: list[dict] = Field(default_factory=list)
    automation: list[dict] = Field(default_factory=list)

    @model_validator(mode='after')
    def references(self):
        numbers = [pattern.number for pattern in self.patterns]
        if len(numbers) != len(set(numbers)):
            raise ValueError('Pattern numbers must be unique')
        for pattern in self.patterns:
            indices = [score.channel_index for score in pattern.scores]
            if len(indices) != len(set(indices)) or any(index >= len(self.channels) for index in indices):
                raise ValueError('Scores must reference unique, existing channels')
        if any(clip.pattern_number is not None and clip.pattern_number not in numbers for clip in self.playlist):
            raise ValueError('Playlist references an undefined pattern')
        return self


def read_json(path):
    return decode_json(Path(path).read_text(encoding='utf-8-sig'))


def register(app, emit, json_option):
    @app.group()
    @json_option
    def project():
        """Inspect, create, and edit explicit saved FL projects."""

    from .project_diff import register as register_diff
    register_diff(project, emit, json_option)
    from .fields import register as register_fields
    register_fields(project, emit, json_option)
    from .timing import register as register_timing
    register_timing(project, emit, json_option)
    from .merge import register as register_merge
    register_merge(project, emit, json_option)
    from .validation import register as register_validation
    register_validation(project, emit, json_option)
    from .snapshot import register as register_snapshot
    register_snapshot(project, emit, json_option)

    @project.command('inspect')
    @click.option('--input', 'source', required=True, type=click.Path(path_type=Path))
    @click.option('--summary', is_flag=True, help='Omit individual note records.')
    @click.option('--settings', is_flag=True, help='Include sampler, envelope, polyphony and stretching fields.')
    @click.option('--section', 'sections', multiple=True, type=click.Choice(['channels', 'patterns', 'playlist', 'mixer', 'automation', 'metadata', 'arrangements', 'controllers', 'markers', 'channel_settings']), help='Decode only these sections; repeat to combine them.')
    @json_option
    def inspect(source, summary, settings, sections):
        doc = Project.read(source)
        data = doc.inspect(not summary, settings, sections)
        emit(Result(command='project inspect', status='verified',
                    verified_scopes=['saved_' + {'patterns': 'notes'}.get(name, name)
                                     for name in data if name in ('channels', 'patterns', 'playlist', 'mixer', 'automation', 'metadata', 'arrangements', 'controllers', 'markers', 'channel_settings')],
                    data=data))

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
        if (after.patterns() != doc.patterns() or after.channels() != doc.channels()
                or after.playlist() != doc.playlist() or after.mixer() != doc.mixer()):
            raise ValueError('Saved project readback differs from the requested composition')
        data.update(file_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                    file_note_count=sum(len(p['notes']) for p in after.patterns().values()), live_applied=False)
        emit(Result(command='project build', status='artifact_ready',
                    verified_scopes=['saved_notes', 'saved_channels', 'saved_playlist', 'saved_mixer'] +
                    (['saved_host_overrides'] if spec.sytrus or spec.plugin_params else []), data=data))

    @project.command('edit')
    @click.option('--input', 'source', required=True, type=click.Path(path_type=Path))
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def edit(source, request, output, dry_run):
        """Apply explicit note/channel/playlist/mixer changes to a new FLP copy."""
        changes = read_json(request)
        if not isinstance(changes, dict) or set(changes) - {'tempo_bpm', 'channels', 'scores', 'patterns', 'playlist', 'mixer', 'effects', 'plugin_params', 'plugin_settings', 'fx_chains', 'sytrus', 'playlist_edits', 'automation', 'metadata', 'arrangements', 'controllers', 'transforms', 'markers'}:
            raise ValueError('Unknown project edit section')
        doc = Project.read(source)
        from .fields import set_metadata, set_arrangement, set_controllers
        set_metadata(doc, changes.get('metadata', {}))
        if 'tempo_bpm' in changes:
            doc.set_tempo(changes['tempo_bpm'])
        for channel in changes.get('channels', []):
            if 'clone_from' in channel:
                from .entities import clone_channel
                if 'index' in channel: raise ValueError('A channel clone uses clone_from instead of index')
                index = clone_channel(doc, channel['clone_from'], channel.get('name'), channel.get('copy_scores', False))
                doc.set_channel(index, {k: v for k, v in channel.items() if k not in ('clone_from', 'name', 'copy_scores')})
            else:
                doc.set_channel(channel['index'], {k: v for k, v in channel.items() if k != 'index'})
        for score in changes.get('scores', []):
            if score.get('mode', 'replace') not in ('append', 'replace'):
                raise ValueError('Score mode must be replace or append')
            doc.replace_notes(score['pattern_number'], score['channel_index'], score['notes'], score.get('mode') == 'append')
        for pattern in changes.get('patterns', []):
            from .entities import edit_pattern
            edit_pattern(doc, pattern)
        from .scores import transform
        for operation in changes.get('transforms', []): transform(doc, operation)
        for arrangement in changes.get('arrangements', []): set_arrangement(doc, arrangement)
        for controllers in changes.get('controllers', []): set_controllers(doc, controllers)
        from .timing import set_markers
        for marker_spec in changes.get('markers', []): set_markers(doc, marker_spec)
        if 'playlist' in changes:
            doc.set_playlist([Clip.model_validate(c).model_dump() for c in changes['playlist']])
        for mixer in changes.get('mixer', []):
            doc.set_mixer(mixer['track'], {k: v for k, v in mixer.items() if k != 'track'})
        for effect in changes.get('effects', []):
            doc.load_effect(effect['track'], effect['slot'], effect['preset'])
        from .mixing import apply_chains, validate_routing
        apply_chains(doc, changes.get('fx_chains', []))
        from .sytrus import set_parameters
        sytrus_changes = [set_parameters(doc, synth['channel'], synth['params']) for synth in changes.get('sytrus', [])]
        validate_routing(doc)
        from .plugin_profiles import apply_parameters
        apply_parameters(doc, changes.get('plugin_params', []))
        from .plugin_state import edit as edit_plugin, describe as describe_plugin
        plugin_settings = [edit_plugin(doc, spec) for spec in changes.get('plugin_settings', [])]
        from .automation import create_curve, write_curve
        for curve in changes.get('automation', []):
            if 'channel' in curve:
                if set(curve) != {'channel', 'points'}:
                    raise ValueError('Editing an existing automation requires channel and points')
                write_curve(doc, curve['channel'], curve['points'])
            else:
                create_curve(doc, curve)
        from .timeline import patch_playlist
        patch_playlist(doc, changes.get('playlist_edits', []))
        data = {'source': str(source.resolve()), 'output': str(output.resolve()),
                'after': doc.inspect(include_settings=any('settings' in c for c in changes.get('channels', []))), 'live_applied': False}
        if sytrus_changes:
            data['sytrus_changes'] = sytrus_changes
        if plugin_settings:
            data['plugin_settings'] = plugin_settings
        if dry_run:
            data.update(applied_count=None, file_effects=[])
            emit(Result(command='project edit', status='planned', data=data))
            return
        doc.save(output)
        readback = Project.read(output)
        observed = readback.inspect(include_settings='channel_settings' in data['after'])
        for item in plugin_settings:
            target = {k: item['after'][k] for k in ('channel', 'track', 'slot') if k in item['after']}
            if describe_plugin(readback, target) != item['after']: raise ValueError('Plugin settings readback mismatch')
        for section in ('patterns', 'channels', 'mixer', 'playlist', 'automation', 'metadata', 'arrangements', 'controllers', 'channel_settings', 'markers'):
            if section not in data['after']: continue
            if observed[section] != data['after'][section]:
                raise ValueError(f'{section} readback mismatch after saving')
        emit(Result(command='project edit', status='artifact_ready',
                    verified_scopes=['saved_notes', 'saved_channels', 'saved_playlist', 'saved_mixer'] +
                    (['saved_plugin_param'] if changes.get('plugin_params') else []) +
                    (['saved_plugin_settings'] if plugin_settings else []) +
                    (['saved_host_overrides'] if sytrus_changes else []) +
                    (['saved_automation'] if changes.get('automation') else []), data=data))

    @app.group('plugin')
    @json_option
    def plugin_group():
        """Read supported saved effect parameters without touching live FL."""

    from .vst3 import register as register_vst3
    register_vst3(plugin_group, emit, json_option)

    @plugin_group.command('settings')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @click.option('--channel', type=click.IntRange(0, 4095))
    @click.option('--track', type=click.IntRange(0, 499))
    @click.option('--slot', type=click.IntRange(0, 9))
    @json_option
    def saved_settings(project, channel, track, slot):
        """Read Wrapper flags, VST settings, small native states and Notebook pages."""
        from .plugin_state import describe
        target = {k: v for k, v in (('channel', channel), ('track', track), ('slot', slot)) if v is not None}
        emit(Result(command='plugin settings', status='verified', verified_scopes=['saved_plugin_settings'],
                    data=describe(Project.read(project), target)))

    @plugin_group.command('presets')
    @click.option('--plugin', required=True, help='Installed plugin folder name, e.g. Sytrus.')
    @click.option('--kind', type=click.Choice(['generator', 'effect']), default='generator')
    @click.option('--search', '--query', default='')
    @click.option('--fl-install', type=click.Path(path_type=Path), default=DEFAULT_INSTALL)
    @click.option('--root', type=click.Path(path_type=Path), help='Optional user preset root containing plugin folders.')
    @click.option('--offset', type=click.IntRange(0), default=0)
    @click.option('--limit', type=click.IntRange(1, 200), default=40)
    @json_option
    def presets(plugin, kind, search, fl_install, root, offset, limit):
        if Path(plugin).name != plugin or plugin in ('.', '..') or '/' in plugin or '\\' in plugin:
            raise ValueError('Plugin must be a folder name, not a path')
        directories = [fl_install / 'Data/Patches/Plugin presets' / ('Generators' if kind == 'generator' else 'Effects') / plugin]
        if root:
            directories.append(root / plugin)
        found = {}
        for directory in directories:
            if directory.is_dir():
                for path in sorted(directory.rglob('*.fst')):
                    relative = path.relative_to(directory)
                    if search.casefold() in str(relative).casefold():
                        found[str(path.resolve())] = {'name': path.stem, 'category': str(relative.parent),
                                                    'path': str(path.resolve())}
        items = list(found.values())
        emit(Result(command='plugin presets', status='verified', verified_scopes=['installed_preset_files'],
                    data={'plugin': plugin, 'kind': kind, 'searched': [str(p) for p in directories], 'total': len(items),
                          'offset': offset, 'next_offset': offset + limit if offset + limit < len(items) else None,
                          'presets': items[offset:offset + limit]}))

    @plugin_group.command('params')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @click.option('--track', type=click.IntRange(0, 125))
    @click.option('--slot', type=click.IntRange(0, 9))
    @click.option('--channel', type=click.IntRange(0, 4095))
    @json_option
    def saved_params(project, track, slot, channel):
        doc = Project.read(project)
        if channel is not None:
            if track is not None or slot is not None:
                raise ValueError('Choose channel or track+slot')
            from .sytrus import parameters
            data = parameters(doc, channel)
        else:
            if track is None or slot is None:
                raise ValueError('Choose channel or track+slot')
            data = doc.plugin_parameters(track, slot)
        emit(Result(command='plugin params', status='verified', verified_scopes=['saved_plugin_param'],
                    data=data))

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
