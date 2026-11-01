"""Addressed native audio previews and their durable model-listening artifacts."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import wave

from .flp import Project

INSTALL = Path('C:/Program Files/Image-Line/FL Studio 2026')


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _automated(project):
    from .automation import read_all
    from .fields import pattern_controllers
    return {a for c in read_all(project) for a in c['target_addresses']} | {
        r['target_address'] for group in pattern_controllers(project) for r in group['records']}


def _graph(project):
    from .mixing import send_address
    tracks = project.mixer()[:-1]
    automated = _automated(project)
    graph = {t['index']: {r['to']: r['level'] for r in t['sends']} for t in tracks}
    dynamic = {(a, b) for a, edges in graph.items() for b in edges
               if send_address(project, a, b) in automated}
    return tracks, graph, dynamic


def _detach_controls(project, addresses):
    """Detach only controls intentionally overridden in this preview copy."""
    addresses = set(addresses)
    links = sum(e.id == 227 and len(e.data) == 20 and struct.unpack_from('<I', e.data, 8)[0] in addresses
                for e in project.events)
    project.events = [e for e in project.events if not (e.id == 227 and len(e.data) == 20
                      and struct.unpack_from('<I', e.data, 8)[0] in addresses)]
    removed = 0
    for event in project.events:
        if event.id == 223:
            if len(event.data) % 12:
                raise ValueError('Unsupported Pattern controller record layout')
            rows = [event.data[i:i+12] for i in range(0, len(event.data), 12)
                    if struct.unpack_from('<I', event.data, i+4)[0] not in addresses]
            removed += len(event.data)//12-len(rows)
            event.data = b''.join(rows)
    return {'controller_links': links, 'pattern_records': removed}


def _neutral_master(project, effects=False):
    from .mixing import track_address
    base = track_address(project, 0)
    detached = _detach_controls(project, {base | 192, base | 193})
    project.set_mixer(0, {'effects_enabled': effects, 'muted': False, 'volume_raw': 12800, 'pan_raw': 0})
    return detached


def _closure(seeds, graph, *, reverse=False):
    result = set(seeds)
    while True:
        more = ({a for a, edges in graph.items() if set(edges) & result} if reverse else
                {b for a in result if a != 0 for b in graph.get(a, {})})
        new = more - result
        if not new:
            return result
        result.update(new)


def isolate_channels(project, selected):
    """Keep target audio and static Mixer sidechain drivers, suppress bypasses."""
    selected = set(selected)
    channels = project.channels()
    tracks, graph, dynamic = _graph(project)
    audible_graph = {a: {b: v for b, v in edges.items() if v > 0 or (a, b) in dynamic}
                     for a, edges in graph.items()}
    audible = _closure({channels[c]['mixer_track'] for c in selected}, audible_graph)
    control = set()
    while True:
        drivers = {a for a, edges in graph.items() for b, v in edges.items()
                   if v == 0 and (a, b) not in dynamic and b in audible | control}
        new = _closure(control | drivers, graph, reverse=True) - audible
        if new == control:
            break
        control = new
    shared = {a for a, edges in graph.items() for b, v in edges.items()
              if a in audible and v == 0 and b in audible | control}
    conflicts = [c['index'] for c in channels if c['type'] != 5 and c['index'] not in selected
                 and c['mixer_track'] in shared]
    if conflicts:
        raise ValueError(f'Sidechain driver shares an audible insert with omitted channels {conflicts}; '
                         'preview its Mixer track or the full song instead')
    for c in channels:
        if c['type'] != 5 and c['index'] not in selected and c['mixer_track'] not in control:
            project.set_channel(c['index'], {'muted': True})
    overridden = set()
    from .mixing import send_address
    for t in tracks:
        a = t['index']
        if a not in audible:
            keep = [b for b, v in graph[a].items()
                    if b in control or (v == 0 and (a, b) not in dynamic and b in audible)]
            overridden.update(send_address(project, a, b) for b in graph[a] if b not in keep)
            project.set_mixer(a, {'routes': keep})
    detached = _detach_controls(project, overridden)
    return {'audible_channels': sorted(selected), 'audible_mixer_tracks': sorted(audible),
            'preserved_control_mixer_tracks': sorted(control),
            'detached_bypass_send_controls': detached,
            'isolation': 'Channel audio plus saved static Mixer sidechain dependencies; original downstream processing',
            'limits': ['Plugin-internal/MIDI control dependencies are not inferred.',
                       'Changed shared bus/Master dynamics do not constitute an exact mix-contribution stem.']}


def isolate_mixer(project, track, master_fx=False):
    """Listen after one insert with all its upstream audio/control input retained."""
    tracks, graph, _ = _graph(project)
    if type(track) is not int or track not in graph:
        raise ValueError('Choose an existing Mixer track')
    if track == 0:
        project.set_mixer(0, {'effects_enabled': master_fx})
        return {'mixer_track': 0, 'isolation': 'Master output', 'preserved_input_tracks': sorted(graph)}
    upstream = _closure({track}, graph, reverse=True)
    if 0 in upstream:
        raise ValueError('Feedback through Master cannot be isolated; preview the full song')
    from .mixing import send_address
    overridden = {send_address(project, track, 0)}
    for t in tracks:
        a = t['index']
        keep = [0] if a == track else [b for b in graph[a] if b in upstream]
        overridden.update(send_address(project, a, b) for b in graph[a] if b not in keep)
        project.set_mixer(a, {'routes': keep})
    project.set_mixer(track, {'sends': [{'to': 0, 'level': 1.0}]})
    detached = _detach_controls(project, overridden)
    master_controls = _neutral_master(project, master_fx)
    return {'mixer_track': track, 'preserved_input_tracks': sorted(upstream),
            'isolation': 'Post-insert output directly to Master; original downstream buses/sends excluded',
            'master_fx': master_fx, 'master_fader': 'unity/center/unmuted in the preview copy',
            'overridden_send_controls': detached, 'neutralized_master_controls': master_controls,
            'limits': ['An isolated nonlinear insert is not a claimed exact contribution to the original full mix.',
                       'Plugin-internal/MIDI control dependencies are not inferred; optional Master FX receive this isolated branch.']}


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer {low}..{high}')
    return value


def _select_arrangement(project, arrangement):
    from .timeline import playlist_events
    if arrangement not in {a for a, _ in playlist_events(project)}:
        raise ValueError('Preview arrangement is absent')
    event = next((e for e in project.events if e.id == 100), None)
    if event is None:
        raise ValueError('Saved project has no selected-arrangement field')
    event.data = arrangement.to_bytes(len(event.data), 'little')


def _solo_playlist(project, arrangement, pattern, length):
    from .timeline import patch_playlist
    from .fields import set_arrangement
    project.set_playlist([{'pattern_number': pattern, 'track': 1, 'start_tick': 0,
                           'length_tick': length}], arrangement)
    patch_playlist(project, [{'arrangement': arrangement, 'clip_index': 0, 'muted': False}])
    set_arrangement(project, {'index': arrangement, 'tracks': [{'track': 1, 'enabled': True}]})


def _retain_clips_with_controls(project, arrangement, clips, selected):
    """Keep other occurrences' controls/sidechains without leaking their music."""
    from .entities import edit_pattern
    from .timeline import patch_playlist
    routing = isolate_channels(project, selected)
    control = {c['index'] for c in project.channels()
               if c['type'] != 5 and c['mixer_track'] in routing['preserved_control_mixer_tracks']}
    clones, edits = {}, []
    for clip in project.playlist():
        if clip['arrangement'] != arrangement or clip['clip_index'] in clips or clip['kind'] == 'automation':
            continue
        if clip['kind'] == 'pattern':
            original = clip['pattern_number']
            if original not in clones:
                number = next((i for i in range(1, 1000) if i not in project.patterns()), None)
                if number is None:
                    raise ValueError('No Pattern identity remains for isolated control occurrences; preview a Mixer track')
                edit_pattern(project, {'number': number, 'clone_from': original, 'name': 'CLI control-only occurrence'})
                for ch in {n['channel_index'] for n in project.patterns()[number]['notes']} - control:
                    if ch is not None:
                        project.replace_notes(number, ch, [])
                clones[original] = number
            edits.append({'arrangement': arrangement, 'clip_index': clip['clip_index'], 'pattern_number': clones[original]})
        elif clip['channel_index'] not in control:
            edits.append({'arrangement': arrangement, 'clip_index': clip['clip_index'], 'muted': True})
    patch_playlist(project, edits)
    routing['control_only_pattern_copies'] = [{'source': a, 'copy': b} for a, b in clones.items()]
    return routing


def prepare_scope(project, request):
    from .entities import edit_pattern
    from .timeline import patch_playlist
    allowed = {'scope', 'channel', 'pattern', 'track', 'kind', 'arrangement', 'notes',
               'processing', 'master_fx', 'occurrence', 'start_tick', 'end_tick',
               'start_seconds', 'end_seconds', 'encoding'}
    if not isinstance(request, dict) or set(request)-allowed:
        raise ValueError('Unknown audio preview field; choose an explicit scope and documented selectors')
    scope = request.get('scope')
    if scope not in ('timbre', 'pattern', 'piano_roll', 'track', 'song'):
        raise ValueError('Preview scope must be timbre, pattern, piano_roll, track or song')
    common = {'scope','arrangement','start_tick','end_tick','start_seconds','end_seconds','encoding'}
    selectors = {'timbre': {'channel','notes','processing'}, 'pattern': {'pattern','occurrence','processing'},
                 'piano_roll': {'pattern','channel','occurrence','processing'},
                 'track': {'track','kind','master_fx'}, 'song': set()}
    if set(request)-common-selectors[scope]:
        raise ValueError('Preview selectors do not match its scope')
    arrangement = request.get('arrangement', next((int.from_bytes(e.data, 'little') for e in project.events if e.id == 100), 0))
    _select_arrangement(project, arrangement)
    info = {'scope': scope, 'arrangement': arrangement}
    channels, patterns = project.channels(), project.patterns()
    selected = None
    if scope in ('timbre', 'piano_roll'):
        channel = _integer(request.get('channel'), 0, len(channels)-1, 'Channel')
        if channels[channel]['type'] not in (0, 2):
            raise ValueError('Timbre/Piano Roll preview requires a generator or Sampler channel')
        info.update(channel=channel, channel_iid=channels[channel]['iid'], channel_name=channels[channel]['name'])
        selected = {channel}
    if scope == 'timbre':
        number = next((i for i in range(1, 1000) if i not in patterns), None)
        if number is None:
            raise ValueError('No unused Pattern number remains for the declared timbre test')
        notes = request.get('notes', [
            {'key': 60, 'velocity': 100, 'start_tick': 0, 'length_tick': project.ppq//2},
            {'key': 60, 'velocity': 100, 'start_tick': project.ppq*2, 'length_tick': project.ppq*2}])
        if not isinstance(notes, list) or not notes:
            raise ValueError('Timbre test notes must be a nonempty array')
        edit_pattern(project, {'number': number, 'name': 'CLI timbre audition'})
        project.replace_notes(number, channel, notes)
        length = max(n['start_tick']+n['length_tick'] for n in project.patterns()[number]['notes'])
        _solo_playlist(project, arrangement, number, length)
        info.update(test_pattern=number, test_notes=project.patterns()[number]['notes'],
                    musical_context='Declared test notes, not the original phrase')
    elif scope in ('pattern', 'piano_roll'):
        number = request.get('pattern')
        if type(number) is not int or number not in patterns:
            raise ValueError('Preview Pattern number is absent')
        notes = patterns[number]['notes']
        if selected is None:
            selected = {n['channel_index'] for n in notes if n['channel_index'] is not None}
        if not any(n['channel_index'] in selected for n in notes):
            raise ValueError('Selected Pattern/Piano Roll contains no target notes')
        info.update(pattern=number, pattern_name=patterns[number]['name'])
        occurrence = request.get('occurrence')
        if occurrence is not None:
            if not isinstance(occurrence, dict) or set(occurrence) != {'clip_index'}:
                raise ValueError('occurrence requires clip_index in the chosen arrangement')
            match = next((c for c in project.playlist() if c['arrangement'] == arrangement and
                          c['clip_index'] == occurrence['clip_index'] and c['pattern_number'] == number), None)
            if match is None:
                raise ValueError('Pattern occurrence does not match the addressed Playlist clip')
            info['routing'] = _retain_clips_with_controls(project, arrangement, {match['clip_index']}, selected)
            info.update(occurrence={k:v for k,v in match.items() if k!='opaque_tail_hex'}, source_start_tick=match['start_tick'],
                        source_end_tick=match['start_tick']+match['length_tick'])
        else:
            length = max(patterns[number].get('length_tick', 0), max(n['start_tick']+n['length_tick'] for n in notes))
            _solo_playlist(project, arrangement, number, length)
            info['musical_context'] = 'Standalone Pattern; Pattern events retained, song Automation Clips not scheduled'
    elif scope == 'track':
        kind = request.get('kind')
        if kind == 'mixer':
            master = request.get('master_fx', request.get('track') == 0)
            if type(master) is not bool:
                raise ValueError('master_fx must be a boolean')
            info['routing'] = isolate_mixer(project, request.get('track'), master)
        elif kind == 'playlist':
            if 'master_fx' in request:
                raise ValueError('master_fx is only a Mixer-track selector')
            track = _integer(request.get('track'), 1, 500, 'Playlist track')
            clips = [c for c in project.playlist() if c['arrangement'] == arrangement]
            targets = [c for c in clips if c['track'] == track and c['kind'] != 'automation' and not c['muted']]
            if not targets:
                raise ValueError('Selected Playlist track contains no active music clips')
            selected = {c['channel_index'] for c in targets if c['kind'] != 'pattern'}
            selected.update(n['channel_index'] for c in targets if c['kind'] == 'pattern'
                            for n in patterns[c['pattern_number']]['notes'] if n['channel_index'] is not None)
            selected.discard(None)
            info['routing'] = _retain_clips_with_controls(project, arrangement,
                {c['clip_index'] for c in targets}, selected)
            info.update(playlist_track=track, selected_clip_indices=[c['clip_index'] for c in targets],
                        source_start_tick=min(c['start_tick'] for c in targets),
                        source_end_tick=max(c['start_tick']+c['length_tick'] for c in targets))
        else:
            raise ValueError('Track preview kind must explicitly be mixer or playlist')
        info['track_kind'] = kind
    processing = request.get('processing', 'generator' if scope == 'timbre' else 'mix')
    if processing not in ('generator', 'mix') or (processing == 'generator' and selected is None):
        raise ValueError('Generator processing is only supported for addressed timbre/Pattern/Piano Roll voices')
    if selected is not None:
        if processing == 'generator':
            for c in project.channels():
                if c['type'] != 5:
                    project.set_channel(c['index'], {'muted': c['index'] not in selected})
                    if c['index'] in selected:
                        project.set_channel(c['index'], {'mixer_track': 0})
            for t in project.mixer()[1:-1]:
                project.set_mixer(t['index'], {'routes': []})
            master_controls = _neutral_master(project)
            info['routing'] = {'audible_channels': sorted(selected), 'processing': 'Generator/internal effects through unity Master; Mixer FX bypassed',
                               'neutralized_master_controls': master_controls}
        else:
            if 'routing' not in info:
                info['routing'] = isolate_channels(project, selected)
    info['processing'] = processing
    info['native_timeline_preserved'] = scope in ('track', 'song') or 'occurrence' in info
    return info


def _wave_slice(source, output, start, end):
    with wave.open(str(source), 'rb') as stream:
        rate, frames = stream.getframerate(), stream.getnframes()
        duration = frames/rate
        stop = duration if end is None else end
        if not 0 <= start < stop <= duration+1/rate:
            raise ValueError(f'Preview interval {start}..{stop}s is outside rendered duration {duration}s')
        a, b = round(start*rate), min(frames, round(stop*rate))
        stream.setpos(a)
        raw = stream.readframes(b-a)
        with wave.open(str(output), 'wb') as out:
            out.setparams(stream.getparams())
            out.writeframes(raw)


def _artifact(path, ident, mime, duration, start=0):
    return {'id': ident, 'path': str(path.resolve()), 'sha256': _sha(path),
            'bytes': path.stat().st_size, 'mime_type': mime,
            'duration_seconds': duration, 'source_start_seconds': start,
            'source_end_seconds': start+duration}


def preview(source, request, output, install=INSTALL, timeout=120, *, dry_run=False, reuse=None, workspace_created=False):
    from .native import render, read_audio
    from .sound_state import rebase_samples, sample_fingerprint
    from .timing import TempoMap
    from .json_output import canonical_json
    source, output = Path(source).resolve(), Path(output).resolve()
    original_sha = _sha(source)
    project = Project.read(source)
    rebase_samples(project, source.parent)
    dependencies = sample_fingerprint(project, source.parent)
    if output.exists() and workspace_created:
        if {p.name for p in output.iterdir()} != {'checkpoint.flp'}:
            raise ValueError('Owned-session preview workspace must contain only its new checkpoint')
    elif output.exists():
        prior = output/'preview.json'
        if prior.is_file():
            data = json.loads(prior.read_text(encoding='utf8'))
            if (data.get('status') == 'ready' and data.get('source', {}).get('sha256') == original_sha
                    and data.get('request') == request and
                    data.get('known_sample_dependencies') == dependencies and
                    all(Path(a['path']).is_file() and _sha(a['path']) == a['sha256'] for a in data.get('artifacts', []))):
                return {**data, 'reused': True, **({'status': 'planned'} if dry_run else {})}
        raise ValueError('Choose a new preview directory; an incomplete or different preview is preserved')
    if not output.parent.is_dir():
        raise ValueError('Preview parent directory must already exist')
    scope = prepare_scope(project, request)
    end_tick = max((c['start_tick']+c['length_tick'] for c in project.playlist()
                    if c['arrangement'] == scope['arrangement'] and not c['muted']), default=0)
    clock = TempoMap(project, end_tick, scope['arrangement'])
    musical = any(k in request for k in ('start_tick', 'end_tick'))
    seconds = any(k in request for k in ('start_seconds', 'end_seconds'))
    if musical and seconds:
        raise ValueError('Choose tick bounds or second bounds, not both')
    start, end = request.get('start_seconds', 0), request.get('end_seconds')
    if musical:
        if clock.reason:
            raise ValueError(f'Tick crop requires known tempo timing ({clock.reason}); supply explicit seconds')
        a = _integer(request.get('start_tick', 0), 0, 0xffffffff, 'start_tick')
        b = _integer(request.get('end_tick', end_tick), a+1, 0xffffffff, 'end_tick')
        start, end = clock.seconds(a), clock.seconds(b)
    elif 'source_start_tick' in scope and not seconds:
        if clock.reason:
            raise ValueError('Occurrence/track bounds require explicit seconds for this tempo map')
        start, end = clock.seconds(scope['source_start_tick']), clock.seconds(scope['source_end_tick'])
    if (any(type(v) not in (int, float) or not math.isfinite(v) for v in [start]+([] if end is None else [end]))
            or start < 0 or end is not None and end <= start):
        raise ValueError('Preview seconds must be finite and 0 <= start < end')
    encoding = request.get('encoding', 'auto')
    if encoding not in ('auto', 'wav', 'mp3'):
        raise ValueError('Preview encoding must be auto, wav or mp3')
    data = {'kind': 'flstudio.audio.preview', 'schema_version': 1, 'status': 'planned',
            'manifest': str(output/'preview.json'), 'request': request,
            'source': {'path': str(source), 'sha256': original_sha, 'saved_checkpoint': True},
            'known_sample_dependencies': dependencies,
            'cache_limits': 'Known channel samples are content-fingerprinted. Plugin-managed external resources and binaries are not exhaustively fingerprinted; use a fresh directory when they change.',
            'scope': scope, 'timeline': {'start_seconds': start, 'end_seconds': end,
                'crop': 'Window of original native playback; no artificial tail or loudness processing'},
            'prepared_project': str(output/'prepared.flp'),
            'prepared_sha256': hashlib.sha256(project.encode()).hexdigest(),
            'artifacts': [], 'listening': {'status': 'not_performed'}, 'reused': False}
    if dry_run:
        return data
    output.mkdir(exist_ok=workspace_created)
    def checkpoint():
        (output/'preview.json').write_text(canonical_json(data)+'\n', encoding='utf8')
    checkpoint()
    try:
        project.save(output/'prepared.flp')
        native = None
        if reuse:
            prior = json.loads(Path(reuse).read_text(encoding='utf8'))
            receipt = prior.get('native_render', {})
            path = Path(receipt.get('output', ''))
            if (prior.get('prepared_sha256') != data['prepared_sha256'] or
                    prior.get('known_sample_dependencies') != dependencies or receipt.get('status') != 'verified'
                    or not path.is_file() or _sha(path) != receipt.get('audio', {}).get('sha256')):
                raise ValueError('Reusable render does not match this prepared project and complete native WAV')
            native = {**receipt, 'reused_from': str(Path(reuse).resolve())}
        if native is None:
            native = render(output/'prepared.flp', output/'native.wav', Path(install), timeout)
        data['native_render'] = native
        checkpoint()
        if native['status'] != 'verified':
            raise ValueError('Native preview failed; inspect preview.json render evidence before retrying in a new directory')
        wav = output/'audio.wav'
        _wave_slice(Path(native['output']), wav, start, end)
        info = native['audio'] if start == 0 and end is None else read_audio(wav)[0]
        audio = _artifact(wav, 'audio', 'audio/wav', info['duration_seconds'], start)
        audio.update(sample_rate=info['sample_rate'], channels=info['channels'],
                     peak_dbfs=info['peak_dbfs'], rms_dbfs=info['rms_dbfs'])
        data['artifacts'].append(audio)
        data['listening_artifact_id'] = 'audio'
        if encoding == 'mp3' or encoding == 'auto' and wav.stat().st_size > 10_000_000:
            ffmpeg = shutil.which('ffmpeg')
            if ffmpeg is None:
                raise ValueError('Listening copy needs installed FFmpeg; use encoding=wav or a smaller preview window')
            mp3 = output/'listening.mp3'
            done = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-i', str(wav),
                                   '-codec:a', 'libmp3lame', '-b:a', '192k', str(mp3)],
                                  capture_output=True, timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if done.returncode:
                raise ValueError('FFmpeg listening conversion failed; the original native WAV is retained')
            encoded = _artifact(mp3, 'listening', 'audio/mpeg', info['duration_seconds'], start)
            encoded['conversion'] = {'source_sha256': audio['sha256'], 'codec': 'MP3/192kbps',
                                     'gain_processing': 'none', 'duration_basis': 'source WAV frames; codec padding may exist'}
            data['artifacts'].append(encoded)
            data['listening_artifact_id'] = 'listening'
        if _sha(source) != original_sha:
            raise ValueError('Source changed during preview; result is not a stable source checkpoint')
        data.update(status='ready', source_preserved=True)
        checkpoint()
        return data
    except BaseException as error:
        data.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed', error=str(error),
                    next_action='Retain this evidence; correct the reported cause and use a new preview directory')
        checkpoint()
        raise


def register(app, emit, json_option):
    import click
    from .contracts import Result
    from .json_output import decode_json
    @app.commands['audio'].command('preview')
    @click.option('--project', type=click.Path(path_type=Path))
    @click.option('--session', type=click.Path(path_type=Path), help='Save a fresh checkpoint of a CLI-owned live session before previewing.')
    @click.option('--request', type=click.Path(path_type=Path), required=True)
    @click.option('--output-dir', type=click.Path(path_type=Path), required=True)
    @click.option('--reuse', type=click.Path(path_type=Path), help='Reuse a matching complete native render from a prior preview manifest.')
    @click.option('--fl-install', type=click.Path(path_type=Path), default=INSTALL)
    @click.option('--timeout', type=click.FloatRange(1, 1800), default=120)
    @click.option('--dry-run', is_flag=True)
    @json_option
    def command(project, session, request, output_dir, reuse, fl_install, timeout, dry_run):
        if (project is None) == (session is None):
            raise ValueError('Choose exactly one saved project or CLI-owned session')
        spec = decode_json(request.read_text(encoding='utf-8-sig'))
        created = False
        if session:
            if dry_run:
                emit(Result(command='audio preview',status='planned',data={
                    'session':str(session.resolve()),'request':spec,'checkpoint_required':True,
                    'target_validation':'Deferred until a fresh owned-session checkpoint',
                    'file_effects':[],'bridge_contacted':False}))
                return
            from .sessions import save
            output_dir.mkdir()
            project = output_dir/'checkpoint.flp'
            save(decode_json(session.read_text(encoding='utf-8-sig')),project)
            created = True
        data = preview(project, spec, output_dir, fl_install, timeout,
                       dry_run=dry_run, reuse=reuse, workspace_created=created)
        if session:
            data['source']['kind'] = 'fresh_owned_session_checkpoint'
            data['source']['session'] = str(session.resolve())
            (output_dir/'preview.json').write_text(json.dumps(data,ensure_ascii=False)+'\n',encoding='utf8')
        emit(Result(command='audio preview', status='planned' if dry_run else 'artifact_ready',
                    verified_scopes=[] if dry_run else ['native_scope_audio', 'saved_project_copy', 'source_preserved'],
                    data=data))
