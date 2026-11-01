"""Agent sound-design tasks with isolated candidates and native FL checkpoints."""
from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
import json
import math
import re
import time

from .flp import Project
from .json_output import canonical_json, decode_json
from .sound_state import state_view, transfer, resources, rebase_samples, exclusive_insert

INSTALL = Path('C:/Program Files/Image-Line/FL Studio 2026')
ROLES = ('bass', 'lead', 'pad', 'pluck', 'percussion', 'texture', 'other')


def read(path):
    return decode_json(Path(path).read_text(encoding='utf-8-sig'))


def write(path, data, *, new=False):
    path = Path(path)
    text = canonical_json(data) + '\n'
    if new:
        with path.open('x', encoding='utf8', newline='\n') as stream:
            stream.write(text)
    else:
        temp = path.with_suffix('.tmp')
        temp.write_text(text, encoding='utf8', newline='\n')
        temp.replace(path)


def _task(path):
    data = read(path)
    if data.get('kind') != 'flstudio.sound-design.task' or data.get('schema_version') != 1:
        raise ValueError('Choose a sound-design task.json produced by prepare')
    return data


def _target_index(task,project):
    matches=[row['index'] for row in project.channels() if row['iid']==task['target']['iid']]
    if len(matches)!=1:
        raise ValueError('Task target channel IID is absent or ambiguous; prepare a new task from the current project')
    return matches[0]


def prepare(source: Path, channel: int, output: Path, brief: str, role='other', constraints=None):
    source, output = source.resolve(), output.resolve()
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Choose a new task directory with an existing parent')
    if not brief.strip() or role not in ROLES:
        raise ValueError('Provide a musical brief and a supported role')
    project = Project.read(source)
    if type(channel) is not int or not 0 <= channel < len(project.channels()):
        raise ValueError('Target channel is absent from the saved project')
    target = project.channels()[channel]
    if target['type'] not in (0, 2):
        raise ValueError('Sound-design targets must be generator or sampler channels')
    notes = []
    for number, pattern in project.patterns().items():
        selected = [n for n in pattern['notes'] if n['channel_index'] == channel]
        if selected:
            notes.append({'pattern_number': number, 'notes': selected})
    if not notes:
        raise ValueError('The target has no actual MIDI notes; supply a real phrase before designing its timbre')
    constraints = constraints or {}
    allowed = {'harmony', 'reference_description', 'reference_audio', 'avoid', 'plugins', 'max_candidates',
               'render_timeout_seconds', 'latency_requirement', 'external_resources', 'must_preserve', 'max_render_seconds'}
    if not isinstance(constraints, dict) or set(constraints) - allowed:
        raise ValueError('Unknown sound task constraint; use documented musical constraints and budgets')
    max_candidates = constraints.get('max_candidates', 6)
    timeout = constraints.get('render_timeout_seconds', 90)
    if type(max_candidates) is not int or not 1 <= max_candidates <= 24 or type(timeout) not in (int,float) or not math.isfinite(timeout) or not 1 <= timeout <= 1800:
        raise ValueError('max_candidates must be 1..24 and render_timeout_seconds 1..1800')
    if constraints.get('reference_audio') and not Path(constraints['reference_audio']).is_file():
        raise ValueError('Reference audio does not exist; correct its path or use reference_description')
    if 'plugins' in constraints and (not isinstance(constraints['plugins'],list) or not constraints['plugins'] or
            any(not isinstance(name,str) or not name.strip() for name in constraints['plugins'])):
        raise ValueError('plugins must be a nonempty list of allowed plugin names')
    rebase_samples(project, source.parent)
    from .snapshot import snapshot
    from .timing import TempoMap
    end = max((c['start_tick']+c['length_tick'] for c in project.playlist()), default=0)
    seconds = TempoMap(project,end).seconds(end)
    maximum = constraints.get('max_render_seconds', 45)
    if type(maximum) not in (int,float) or not math.isfinite(maximum) or maximum <= 0:
        raise ValueError('max_render_seconds must be a finite positive duration')
    if seconds is None or seconds <= 0 or seconds > maximum:
        raise ValueError('Prepare a bounded actual musical excerpt within max_render_seconds; nonlinear/ambiguous tempo requires an explicit short excerpt')
    for item in project.channels():
        if item.get('sample_path') and not Path(item['sample_path']).is_file():
            raise ValueError(f'Missing channel sample {item["sample_path"]}; locate it before preparing a sound task')
    output.mkdir()
    (output/'candidates').mkdir()
    # Exact source for later preconditions/undo; relocated work copy rebases
    # known relative samples without altering their bytes.
    (output/'original.flp').write_bytes(project.source)
    import shutil
    asset_rows=[]; copied={}
    for item in project.channels():
        value=item.get('sample_path')
        if not value: continue
        sample=Path(value)
        if not sample.is_file():
            raise ValueError(f'Missing channel sample {sample}; locate it before preparing a sound task')
        if str(sample) not in copied:
            assets=output/'assets'; assets.mkdir(exist_ok=True)
            target_path=assets/f'{len(copied):03d}-{sample.name}'
            shutil.copyfile(sample,target_path)
            copied[str(sample)]=target_path
            asset_rows.append({'original':str(sample.resolve()),'copy':str(target_path.resolve())})
        project.set_channel(item['index'],{'sample_path':str(copied[str(sample)])})
    project.save(output/'context.flp')
    data = {'kind': 'flstudio.sound-design.task', 'schema_version': 1,
            'task_file': str(output/'task.json'), 'source': str(source),
            'original_project': str(output/'original.flp'), 'context_project': str(output/'context.flp'),
            'role': role, 'brief': brief, 'target': target, 'phrase': notes,
            'context': snapshot(project, detail=True, limit=32, budget=14000),
            'constraints': constraints, 'budget': {'max_candidates':max_candidates,'render_timeout_seconds':timeout},
            'duration_seconds':seconds, 'resources':resources(project, source.parent),
            'bundled_samples':asset_rows,
            'assumptions': ['Preserve all scores, Playlist and other parts; change only the target timbre and explicitly requested dedicated insert effects.',
                            'The saved excerpt is the authoritative MIDI/rhythm/context; it is not the unsaved editor.',
                            'Signal analysis is available; subjective listening requires a listener or an audio-capable agent.'],
            'handoff': {'run': 'sound-design candidate --task TASK --request CANDIDATE.json',
                        'audition': 'sound-design audition --task TASK --candidate ID',
                        'compare': 'sound-design compare --task TASK --candidate ID --candidate OTHER --output-dir NEW',
                        'apply': 'sound-design apply --task TASK --candidate ID --project CURRENT.flp --output NEW.flp'}}
    write(output/'task.json', data, new=True)
    return data


def _candidate_folder(task, identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,47}',identifier) or identifier.upper() in {'CON','PRN','AUX','NUL','COM1','LPT1'}:
        raise ValueError('Candidate id must be a short lowercase identifier, not a path')
    return Path(task['task_file']).parent/'candidates'/identifier


@contextmanager
def _operation_lock(task_file, identifier):
    """One coordinator per candidate; OS locks release even after interruption."""
    import msvcrt
    task = _task(task_file)
    folder = _candidate_folder(task,identifier)
    with (folder.parent/(identifier+'.lock')).open('a+b') as stream:
        if not stream.tell(): stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            raise ValueError('This candidate is active in another process; query status or wait before resuming it') from None
        try:
            yield
        finally:
            stream.seek(0); msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)


def _observe(bridge, target, changes):
    info = bridge.call('cli_plugin_info', target)
    values = []
    for at in range(0, len(changes), 128):
        values.extend(bridge.call('cli_plugin_read', {**target,'params':[c['param'] for c in changes[at:at+128]]})['params'])
    return {'identity':info,'params':values}


def _design_fields(view):
    """Semantic fields, omitting container/profile upgrades on native load."""
    # FL's V2->V3 factory import writes 0x01000000 into legacy point flags.
    # Those raw flags are not requested edit fields. Compare the exposed
    # semantic envelope/oscillator fields here; keep all raw observations and
    # compare the entire native blob separately across the cold reopen.
    return {'matrix':view['matrix'],'outputs':view['outputs'],
            'operators':[{k:v for k,v in row.items() if k!='volume_envelope_points'} for row in view['operators']]}


def _design_equal(left,right):
    if type(left) in (int,float) and type(right) in (int,float):
        return abs(left-right)<=1e-6
    if isinstance(left,dict) and isinstance(right,dict):
        return set(left)==set(right) and all(_design_equal(left[k],right[k]) for k in left)
    if isinstance(left,list) and isinstance(right,list):
        return len(left)==len(right) and all(_design_equal(a,b) for a,b in zip(left,right))
    return left==right


def _edit(project, channel, request):
    before_identity=project.channels()[channel]
    if request.get('plugin_preset'):
        project.set_channel(channel, {'plugin_preset':request['plugin_preset']})
    if request.get('sytrus_design'):
        from .sytrus_design import apply_design
        apply_design(project, channel, request['sytrus_design'])
    if request.get('sytrus'):
        from .sytrus import set_parameters
        set_parameters(project,channel,request['sytrus'])
    if request.get('channel_settings'):
        project.set_channel(channel, {'settings':request['channel_settings']})
    if request.get('channel_volume_raw') is not None:
        project.set_channel(channel, {'volume_raw':request['channel_volume_raw']})
    if request.get('fx_chain') is not None:
        if not exclusive_insert(project, channel):
            raise ValueError('FX design needs an exclusive non-Master target insert; assign one before preparing the task')
        from .mixing import apply_chains
        apply_chains(project,[{'track':project.channels()[channel]['mixer_track'],'slots':request['fx_chain']}])
    if request.get('effect_params'):
        from .plugin_profiles import apply_parameters
        track = project.channels()[channel]['mixer_track']
        if not exclusive_insert(project, channel):
            raise ValueError('Effect edits require a dedicated target insert')
        if not isinstance(request['effect_params'],list) or any(not isinstance(item,dict) or set(item)-{'slot','param','value','value_raw'} for item in request['effect_params']):
            raise ValueError('Candidate effect_params choose only slot/param/value or value_raw on the target insert')
        apply_parameters(project,[{'track':track,**item} for item in request['effect_params']])
    from .sound_state import check_plugin_bindings
    check_plugin_bindings(project,channel,before_identity)


def candidate(task_file: Path, request: dict, install=INSTALL, resume=False):
    with _operation_lock(task_file,request.get('id') if isinstance(request,dict) else None):
        return _candidate(task_file,request,install,resume)


def _candidate(task_file: Path, request: dict, install=INSTALL, resume=False):
    from .sessions import start, save, stop_worker
    from .live import Bridge
    task = _task(task_file)
    if not isinstance(request,dict) or set(request) - {'id','description','mechanisms','plugin_preset','params','sytrus','sytrus_design','channel_settings','channel_volume_raw','fx_chain','effect_params','resources','tradeoffs','parent'}:
        raise ValueError('Candidate accepts id, description, mechanisms, plugin_preset/params/sytrus/sytrus_design/channel_settings/channel_volume_raw/fx_chain/effect_params/resources/tradeoffs/parent')
    if not isinstance(request.get('description'),str) or not request['description'].strip() or not isinstance(request.get('mechanisms'),list) or not request['mechanisms']:
        raise ValueError('Describe the candidate and its substantive synthesis/envelope/space mechanisms')
    changes = request.get('params', [])
    if not isinstance(changes,list) or len(changes)>128:
        raise ValueError('Candidate params must be an array of at most 128 targeted writes')
    for change in changes:
        if not isinstance(change,dict) or set(change)-{'param','value','expect'} or not {'param','value'} <= set(change):
            raise ValueError('Each parameter requires param/value and optional expect; discover names or indices with live plugin-find')
        if type(change['param']) not in (str,int) or isinstance(change['param'],str) and not change['param'] or isinstance(change['param'],int) and change['param']<0:
            raise ValueError('Parameter selectors must be exact names or nonnegative integer indices')
        for key in ('value','expect'):
            if key in change and (type(change[key]) not in (int,float) or not math.isfinite(change[key]) or not 0 <= change[key] <= 1):
                raise ValueError('Host parameter values/expectations must be finite normalized 0..1; consult plugin units instead of passing Hz or milliseconds directly')
    declared = request.get('resources', [])
    if not isinstance(declared,list) or any(not isinstance(p,str) or not Path(p).is_file() for p in declared):
        raise ValueError('Candidate resources must list existing files; locate missing samples/wavetables/IRs before designing')
    folder = _candidate_folder(task, request.get('id'))
    channel = task['target']['index']
    if folder.exists():
        if not resume:
            raise ValueError('Candidate exists; use --resume with the identical request or choose a new id')
        report = read(folder/'candidate.json')
        if report['request'] != request:
            raise ValueError('Resume request differs; branch under a new candidate id')
        if report['phase'] == 'ready':
            return report
        old_worker = report.get('worker')
        if old_worker:
            stop_worker(old_worker)
        report['attempt'] += 1
    else:
        if sum(p.is_dir() for p in folder.parent.iterdir()) >= task['budget']['max_candidates']:
            raise ValueError('Candidate budget reached; compare the current branches or prepare a new task with an explicit larger budget')
        folder.mkdir()
        report = {'id':request['id'],'request':request,'phase':'preparing','attempt':1,
                  'task_file':str(task_file.resolve()), 'subjective_listening':'not_performed',
                  'history':[], 'artifact':str(folder/'sound.flp')}
        write(folder/'candidate.json', report, new=True)
    def checkpoint(phase, **data):
        report.update(phase=phase, **data)
        report['history'].append({'phase':phase,'at':time.time(),'attempt':report['attempt']})
        write(folder/'candidate.json', report)
    worker = None
    try:
        if declared and not report.get('declared_resources'):
            import shutil
            assets=folder/'assets'; assets.mkdir(exist_ok=True)
            copied=[]
            for index,path in enumerate(declared):
                target_path=assets/f'{index:03d}-{Path(path).name}'
                shutil.copyfile(path,target_path)
                copied.append({'original':str(Path(path).resolve()),'copy':str(target_path.resolve()),
                               'plugin_internal_rebinding':'not_proven; keep original path or explicitly reload the bundled file in the plugin'})
            report['declared_resources']=copied
        native = folder/'sound.flp'
        if native.exists():
            try:
                Project.read(native)
            except (ValueError,OSError):
                native.rename(folder/f'incomplete-{report["attempt"]}.flp')
        if not native.exists():
            base = Path(task['context_project'])
            if request.get('parent'):
                parent = read(_candidate_folder(task,request['parent'])/'candidate.json')
                if parent['phase'] != 'ready': raise ValueError('Branch parent must have a verified saved checkpoint')
                base = Path(parent['artifact'])
            project = Project.read(base)
            _edit(project, channel, request)
            allowed_plugins=task['constraints'].get('plugins')
            identity=project.channels()[channel]
            plugin_name=(identity.get('wrapped_plugin') or {}).get('name',identity['plugin'])
            if allowed_plugins and plugin_name.casefold() not in {name.casefold() for name in allowed_plugins}:
                raise ValueError(f'Plugin {plugin_name!r} is outside this task\'s allowed plugins; branch with an allowed source')
            if request.get('sytrus_design'):
                from .sytrus_design import inspect_design
                report['planned_design']=inspect_design(project,channel)
            if request.get('sytrus'):
                from .sytrus import parameters
                names={change['param'] for change in request['sytrus']}
                report['planned_sytrus_host_controls']=[row for row in parameters(project,channel)['params'] if row['param'] in names or row['index'] in names]
            working = project.save(folder/f'edit-{report["attempt"]}.flp')
            worker = start(working,folder/f'worker-{report["attempt"]}',install)
            checkpoint('editing',worker=worker)
            bridge = Bridge(session=worker)
            target = {'channel':channel}
            before = _observe(bridge,target,changes)
            if task['constraints'].get('plugins') and before['identity']['plugin'] not in task['constraints']['plugins']:
                raise ValueError('Candidate uses a plugin outside the task allow-list')
            transactions = []
            for at in range(0,len(changes),32):
                queued = bridge.call('cli_plugin_apply',{**target,'changes':changes[at:at+32]})
                job = bridge.wait_plugin_job(queued['id'],len(changes[at:at+32]))
                transactions.append(job)
                checkpoint('editing',transactions=transactions)
                if job['state'] != 'verified':
                    raise ValueError('Host parameter write was not verified; inspect transactions and branch from the last saved parent')
            after = _observe(bridge,target,changes)
            checkpoint('host_verified',host_before=before,host_after=after,transactions=transactions)
            saved = save(worker,native)
            checkpoint('saved',saved=saved)
            stop_worker(worker); worker = None
        # Always reopen a newly saved candidate, even when the host echoed all
        # requested values. Discrete controls may canonicalize only on load.
        worker = start(native,folder/f'reopen-{report["attempt"]}',install)
        checkpoint('reopening',worker=worker)
        reopened = _observe(Bridge(session=worker),{'channel':channel},changes)
        roundtrip = folder/f'reopened-{report["attempt"]}.flp'
        save(worker,roundtrip)
        before_doc, after_doc = Project.read(native),Project.read(roundtrip)
        from .sound_state import channel_events
        a = [e.data for e in channel_events(before_doc,channel) if e.id==213]
        b = [e.data for e in channel_events(after_doc,channel) if e.id==213]
        matches = []
        for change, observed in zip(changes,reopened['params']):
            matches.append({'param':observed['i'],'name':observed['name'],'requested':change['value'],
                            'reopened':observed['v'],'display':observed['s'],
                            'matches_requested':abs(observed['v']-change['value'])<=.0001})
        identities = report.get('host_after',{}).get('identity') == reopened['identity']
        bindings = [p['name'] for p in report.get('host_after',{}).get('params',[])] == [p['name'] for p in reopened['params']]
        stable = identities and bindings and all(p['matches_requested'] for p in matches)
        reason=None if stable else 'reopened_host_value_or_identity_mismatch'
        complete_state_equal=state_view(before_doc,channel)==state_view(after_doc,channel)
        if not complete_state_equal:
            stable=False
            reason='reopened_complete_sound_state_mismatch'
        if report.get('planned_design'):
            from .sytrus_design import inspect_design
            saved_design=inspect_design(before_doc,channel)
            reopened_design=inspect_design(after_doc,channel)
            design_stable=_design_equal(_design_fields(report['planned_design']),_design_fields(saved_design)) and _design_equal(_design_fields(saved_design),_design_fields(reopened_design))
            report.update(saved_design=saved_design,reopened_design=reopened_design,design_fields_verified=design_stable)
            stable=stable and design_stable
            if not design_stable: reason='saved_sytrus_design_mismatch'
        if report.get('planned_sytrus_host_controls'):
            from .sytrus import parameters
            saved_controls={row['index']:row['value_raw'] for row in parameters(before_doc,channel)['params']}
            reopened_controls={row['index']:row['value_raw'] for row in parameters(after_doc,channel)['params']}
            raw_checks=[{'param':row['param'],'requested_raw':row['value_raw'],'saved_raw':saved_controls[row['index']],
                         'reopened_raw':reopened_controls[row['index']],
                         'matches_requested':row['value_raw']==saved_controls[row['index']]==reopened_controls[row['index']]}
                        for row in report['planned_sytrus_host_controls']]
            report['sytrus_host_checks']=raw_checks
            if not all(row['matches_requested'] for row in raw_checks):
                stable=False; reason='saved_sytrus_host_control_mismatch'
        if request.get('channel_volume_raw') is not None:
            wanted=request['channel_volume_raw']
            saved_level,reopened_level=before_doc.channels()[channel]['volume_raw'],after_doc.channels()[channel]['volume_raw']
            report['channel_volume_check']={'requested_raw':wanted,'saved_raw':saved_level,'reopened_raw':reopened_level,
                                            'matches_requested':wanted==saved_level==reopened_level}
            if not report['channel_volume_check']['matches_requested']:
                stable=False; reason='saved_channel_volume_mismatch'
        checkpoint('ready' if stable else 'unconfirmed', reopened=reopened, parameter_checks=matches,
                   reason_code=reason,
                   full_plugin_blob_equal_after_reopen=a==b,
                   complete_sound_state_equal_after_reopen=complete_state_equal,
                   resources=resources(before_doc, folder), source_preserved=True,
                   state_scope='Native FLP containing complete channel/host/envelope/FX state; plugin-internal external assets remain declared dependencies',
                   message=None if stable else 'A requested field or complete sound state was not retained after native saving/reopening. Compare planned_design/saved_design, sytrus_host_checks or parameter_checks; branch with a canonical value or correct the target before delivery.')
    except KeyboardInterrupt:
        checkpoint('interrupted',message='Resume this request; a saved checkpoint is reused, otherwise a new isolated attempt starts from its parent')
        raise
    except (ValueError,RuntimeError,OSError) as exc:
        checkpoint('failed',message=str(exc),next_action='Inspect candidate.json; use --resume with the same request or branch from a saved parent under a new id')
    finally:
        if worker:
            report['worker_stop'] = stop_worker(worker)
            write(folder/'candidate.json',report)
    return report


def audition(task_file, identifier, install=INSTALL, repeats=2, timeout=None):
    with _operation_lock(task_file,identifier):
        return _audition(task_file,identifier,install,repeats,timeout)


def _audition(task_file, identifier, install=INSTALL, repeats=2, timeout=None):
    from .native import render
    from .sound_audio import analyze, compare, overlap, _numpy
    _numpy()
    task = _task(task_file)
    folder = _candidate_folder(task,identifier)
    report = read(folder/'candidate.json')
    if report['phase'] != 'ready':
        raise ValueError('Candidate is not ready; inspect/repair its host and reopen checks first')
    if type(repeats) is not int or not 2 <= repeats <= 5:
        raise ValueError('Use 2..5 repeat renders to observe random oscillator/modulation variability')
    timeout=task['budget']['render_timeout_seconds'] if timeout is None else timeout
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 1<=timeout<=task['budget']['render_timeout_seconds']:
        raise ValueError('Audition timeout must be at least 1 second and within the task render-time budget')
    source = Project.read(report['artifact'])
    channel = task['target']['index']
    output = folder/'audio'
    output.mkdir(exist_ok=True)
    progress_path = output/'audition.json'
    progress = read(progress_path) if progress_path.exists() else {'kind':'flstudio.sound-design.audition','candidate':identifier,'renders':{},'subjective_listening':'not_performed'}
    for mode in ('context','solo','rest','reopened'):
        doc = Project.read(report['artifact'] if mode!='reopened' else folder/f'reopened-{report["attempt"]}.flp')
        if mode in ('solo','rest'):
            for ch in doc.channels():
                if ch['type']==5: continue
                if mode=='solo' and ch['index'] != channel or mode=='rest' and ch['index']==channel:
                    doc.set_channel(ch['index'], {'muted':True})
        project_file = output/(mode+'.flp')
        if not project_file.exists(): doc.save(project_file)
        for index in range(repeats if mode=='context' else 1):
            key = mode + (f'-{index+1}' if mode=='context' else '')
            previous=progress['renders'].get(key,{})
            if previous.get('status')=='verified':
                if 'analysis' not in previous:
                    previous['analysis']=analyze(Path(previous['output']))
                    write(progress_path,progress)
                continue
            wav = output/(key+'.wav')
            if wav.exists():
                # An interrupted worker may leave a partial artifact. Keep it
                # as evidence and use a fresh output rather than overwrite it.
                wav = output/(key+f'-retry-{time.time_ns()}.wav')
            result = render(project_file,wav,install,timeout,allow_silence=mode=='rest')
            progress['renders'][key] = result
            write(progress_path,progress)
            if result['status']!='verified':
                progress.update(status='failed',next_action='Inspect worker_windows/source dependencies, then rerun audition; verified renders are retained')
                write(progress_path,progress)
                return progress
            progress['renders'][key]['analysis'] = analyze(wav)
            write(progress_path,progress)
    paths = {k:Path(v['output']) for k,v in progress['renders'].items()}
    durations={key:value['analysis']['duration_seconds'] for key,value in progress['renders'].items()}
    measured_tail_delta=max(abs(durations['context-1']-durations[f'context-{i}']) for i in range(2,repeats+1))
    tail_limit=min(.5,max(.02,measured_tail_delta*2))
    repeats_evidence = [compare(paths['context-1'],paths[f'context-{i}'],tail_tolerance_seconds=tail_limit) for i in range(2,repeats+1)]
    reopen = compare(paths['context-1'],paths['reopened'],tail_tolerance_seconds=tail_limit)
    # Tolerance is reported, not used to call two perceptually different
    # sounds equivalent. Compare against measured within-state variability.
    rms_limit = max(.15,max((p.get('rms_difference_db',0) for p in repeats_evidence),default=0)*2)
    spectrum_limit = max(.015,max((p.get('spectral_cosine_distance',0) for p in repeats_evidence),default=0)*2)
    reproducible = reopen.get('comparable') and reopen['rms_difference_db']<=rms_limit and reopen['spectral_cosine_distance']<=spectrum_limit
    progress.update(status='verified' if reproducible else 'unknown',
                    next_action=None if reproducible else 'Inspect native state and repeat/reopen signal differences; raw renders are retained',
                    repeat_comparisons=repeats_evidence,reopen_comparison=reopen,
                    reopen_signal_check={'passed':bool(reproducible),'rms_tolerance_db':rms_limit,'spectral_cosine_tolerance':spectrum_limit,
                                         'tail_tolerance_seconds':tail_limit,'observed_repeat_duration_variability_seconds':measured_tail_delta,
                                         'basis':'2x measured same-state variability, with .15dB/.015/20ms engineering floors and a 0.5s tail cap. Same-start analysis padding only; not a perceptual-equivalence test'},
                    context_occupancy=overlap(paths['solo'],paths['rest'],task['duration_seconds']),
                    raw_audio_preserved=True)
    write(progress_path,progress)
    return progress


def compare_candidates(task_file, identifiers, output):
    from .sound_audio import matched_previews
    task = _task(task_file)
    if len(identifiers)<2 or len(set(identifiers))!=len(identifiers):
        raise ValueError('Compare at least two distinct candidate ids')
    rows, paths = [], {'solo':[],'context':[]}
    for identifier in identifiers:
        folder = _candidate_folder(task,identifier)
        candidate_report, audio = read(folder/'candidate.json'),read(folder/'audio/audition.json')
        if candidate_report['phase']!='ready' or audio.get('status')!='verified':
            raise ValueError(f'{identifier} lacks verified native save/reopen/audio evidence; inspect and audition it first')
        for mode,key in (('solo','solo'),('context','context-1')):
            paths[mode].append(Path(audio['renders'][key]['output']))
        rows.append({'id':identifier,'description':candidate_report['request']['description'],
                     'mechanisms':candidate_report['request']['mechanisms'],'tradeoffs':candidate_report['request'].get('tradeoffs',[]),
                     'artifact':candidate_report['artifact'],'observations':str(folder/'audio/audition.json')})
    output = Path(output).resolve()
    if output.exists() or not output.parent.is_dir(): raise ValueError('Choose a new comparison directory')
    output.mkdir()
    previews = {mode:matched_previews(files,output/mode,task['duration_seconds']) for mode,files in paths.items()}
    data = {'kind':'flstudio.sound-design.comparison','candidates':rows,'previews':previews,
            'subjective_listening':'not_performed','recommendation':None,
            'decision_required':'Compare both matched solo and actual-context excerpts. Record the listener/reasons and tradeoffs; signal proxies alone do not rank musical quality.'}
    write(output/'comparison.json',data,new=True)
    return data


def apply_candidate(task_file,identifier,source,output,include_fx=True,undo=False):
    task = _task(task_file)
    folder = _candidate_folder(task,identifier)
    report = read(folder/'candidate.json')
    if report['phase']!='ready': raise ValueError('Choose a ready candidate with a native checkpoint')
    original, candidate_doc, target = Project.read(task['original_project']),Project.read(report['artifact']),Project.read(source)
    channel = _target_index(task,target)
    original_channel,candidate_channel=_target_index(task,original),_target_index(task,candidate_doc)
    expected = candidate_doc if undo else original
    expected_channel=candidate_channel if undo else original_channel
    if state_view(target,channel,include_fx)!=state_view(expected,expected_channel,include_fx):
        raise ValueError('Target sound changed since this task. Prepare a new task from the current project; no output was written')
    donor = original if undo else candidate_doc
    before_notes, before_playlist = target.patterns(),target.playlist()
    scope = transfer(target,channel,donor,original_channel if undo else candidate_channel,include_fx)
    if before_notes!=target.patterns() or before_playlist!=target.playlist(): raise ValueError('Sound application changed musical content')
    target.save(output)
    saved = Project.read(output)
    if state_view(saved,channel,include_fx)!=state_view(target,channel,include_fx): raise ValueError('Sound state readback differed')
    return {'output':str(Path(output).resolve()),'candidate':identifier,'undo':undo,'scope':scope,
            'state_readback_equal':True,'live_editor_modified':False,
            'undo_command':None if undo else f'sound-design apply --task "{task_file}" --candidate {identifier} --project "{Path(output).resolve()}" --output NEW.flp --undo',
            'redo_command':f'sound-design apply --task "{task_file}" --candidate {identifier} --project "{Path(output).resolve()}" --output NEW.flp' if undo else None,
            'next_action':'Use the output as the next project checkpoint; render or reopen it before final musical acceptance'}


def support(project,channel):
    doc=Project.read(project)
    if type(channel) is not int or not 0 <= channel < len(doc.channels()):
        raise ValueError('Choose an existing saved channel index')
    info=doc.channels()[channel]
    plugin=(info.get('wrapped_plugin') or {}).get('name',info['plugin'])
    layers={'parameter_names':'requires an addressed live observation; names alone are not control evidence',
            'host_writes':'candidate records independent readback and rejects unconfirmed writes',
            'audio_effect':'audition provides raw solo, actual context, accompaniment, repeated and reopened renders; inspect before/after',
            'complete_state':'native FLP includes opaque plugin, channel host settings and FX. External plugin resources remain declared dependencies'}
    adapter='generic-host'
    limitations=['Parameters absent from FL host API cannot be changed through generic normalized writes',
                 'Discrete controls may quantize only on reload; reopened checks are separate from host echo',
                 'No generic enumeration of hidden modulation routes, internal FX or plugin-internal assets',
                 'No subjective hearing is claimed by signal metrics']
    if plugin.casefold()=='sytrus':
        adapter='sytrus-native-design + saved-host-controls'
        from .sytrus_design import inspect_design,LIMITATIONS
        try:
            observed=inspect_design(doc,channel)
            deep={'available_on_current_state':True,'profile':observed['profile']}
        except ValueError as exc:
            deep={'available_on_current_state':False,'reason':str(exc),'next_action':'Intentionally init a new candidate from local Default, or use native UI/capture; do not patch this preset layout'}
        deep.update(operations=['6x6 FM/RM operator matrix','direct operator OUT','operator ratio','SH modifier','first32 harmonic coefficients','four-point volume envelope with explicit enable'],limitations=LIMITATIONS)
        limitations.append('Deep Sytrus design is restricted to the explicitly validated native layouts/fields; matrix knobs are not host automation parameters')
    elif plugin=='Surge XT':
        limitations.append('FM routing/oscillator/filter enum values are plugin-version-specific; normalized continuous values are not physical units')
    return {'plugin':plugin,'target':info,'adapter':adapter,'deep_adapter':deep if plugin.casefold()=='sytrus' else None,'evidence_layers':layers,'limitations':limitations,
            'dedicated_insert':exclusive_insert(doc,channel),'resources':resources(doc,Path(project).parent)}


def knowledge(search='',identifier=None):
    from importlib.resources import files
    root=Path(__file__).parents[2]/'docs/sound-design/knowledge'
    if root.is_dir():
        recipes=read(root/'recipes.json'); source_data=read(root.parent/'sources.json')
    else:
        root=files('flstudio_cli').joinpath('knowledge')
        recipes=decode_json(root.joinpath('recipes.json').read_text(encoding='utf8'))
        source_data=decode_json(root.joinpath('sources.json').read_text(encoding='utf8'))
    rows=[row for row in recipes['recipes'] if (not identifier or row['id']==identifier)
          and all(term in canonical_json(row).casefold() for term in search.casefold().split())]
    if identifier and not rows: raise ValueError('Unknown knowledge recipe id; list sound-design knowledge first')
    if not search and not identifier:
        return {'recipes':[{'id':r['id'],'word':r['word'],'mechanism':r['mechanism'],'sources':r['sources']} for r in rows],
                'execution_status':recipes['status'],'hint':'Use --id for actions, units, validation and source evidence, or --search with a listening word/mechanism'}
    cited={ident for row in rows for ident in row['sources']}
    return {'recipes':rows,'sources':[s for s in source_data['sources'] if s['id'] in cited],
            'unit_rule':recipes['unit_rule'],'execution_status':recipes['status'],
            'note':'These source-derived plugin actions require a validated adapter mapping. Documented mechanics, local execution evidence and listening evidence are separate.'}


def capture(task_file,session_file,identifier,description,mechanisms,install=INSTALL):
    """Capture a CLI-owned native/UI edit; keep the caller's worker running."""
    from .sessions import save,start,stop_worker
    from .live import Bridge
    task=_task(task_file)
    session=read(session_file)
    if not session.get('owner_marker','').startswith('__FLCLI_OWNED__:') or session.get('desktop_mode')!='private':
        raise ValueError('Capture requires a CLI-owned private session')
    folder=_candidate_folder(task,identifier)
    with _operation_lock(task_file,identifier):
        if folder.exists(): raise ValueError('Capture id exists; choose a new checkpoint id')
        if sum(p.is_dir() for p in folder.parent.iterdir())>=task['budget']['max_candidates']:
            raise ValueError('Candidate budget reached')
        if not description.strip() or not mechanisms: raise ValueError('Describe this checkpoint and its actual design mechanisms')
        folder.mkdir()
        bridge=Bridge(session=session)
        observation=_observe(bridge,{'channel':task['target']['index']},[])
        # Compare with a native-saved baseline: loading an older factory FLP
        # legitimately upgrades metadata. Never use that as a reason to admit
        # edits to the accompaniment, tempo, automation or shared effects.
        saved=save(session,folder/'captured.flp')
        baseline_worker=start(Path(task['context_project']),folder/'baseline-worker',install)
        try:
            save(baseline_worker,folder/'baseline.flp')
        finally:
            stop_worker(baseline_worker)
        baseline,current=Project.read(folder/'baseline.flp'),Project.read(folder/'captured.flp')
        channel=_target_index(task,current)
        include_fx=exclusive_insert(baseline,channel)
        masked=Project.read(folder/'captured.flp')
        transfer(masked,channel,baseline,_target_index(task,baseline),include_fx)
        from .project_diff import compare
        before_view,after_view=baseline.inspect(include_settings=True),masked.inspect(include_settings=True)
        for view in (before_view,after_view):
            # FL advances its work timer during every native save.
            for key in ('work_days','work_seconds'): view['metadata'].pop(key,None)
        differences=compare(before_view,after_view)
        opaque_equal=len(baseline.channels())==len(masked.channels()) and all(
            state_view(baseline,i)==state_view(masked,i) for i in range(len(baseline.channels())))
        capture_check={'parsed_context_diff':differences,'complete_other_sound_states_equal':opaque_equal,
                       'raw_capture':str(folder/'captured.flp'),'native_baseline':str(folder/'baseline.flp')}
        write(folder/'capture.json',capture_check,new=True)
        if not differences['equal'] or not opaque_equal:
            raise ValueError(f'Capture changed the fixed context outside the target sound; inspect {folder/"capture.json"}, restore the context and capture under a new id')
        (folder/'sound.flp').write_bytes((folder/'captured.flp').read_bytes())
        saved['output']=str(folder/'sound.flp')
        report={'id':identifier,'phase':'saved','attempt':0,'request':{'id':identifier,'description':description,'mechanisms':list(mechanisms)},
                'task_file':str(Path(task_file).resolve()),'artifact':str(folder/'sound.flp'),
                'host_before':observation,'host_after':observation,'saved':saved,'history':[],
                'captured_from':str(Path(session_file).resolve()),'original_worker_stopped':False,'subjective_listening':'not_performed'}
        write(folder/'candidate.json',report,new=True)
    return candidate(task_file,report['request'],install,resume=True)


def _candidate_summary(data):
    return {k:data[k] for k in ('id','phase','attempt','artifact','reason_code','message','parameter_checks','sytrus_host_checks','channel_volume_check','full_plugin_blob_equal_after_reopen','complete_sound_state_equal_after_reopen','design_fields_verified','source_preserved') if k in data} | {
        'observations':str(Path(data['artifact']).parent/'candidate.json'),
        'subjective_listening':data.get('subjective_listening','not_performed')}


def _audition_summary(data,folder):
    return {k:data[k] for k in ('status','reopen_signal_check','reopen_comparison','repeat_comparisons','context_occupancy','next_action') if k in data} | {
        'observations':str(folder/'audio/audition.json'),
        'audio':{key:value.get('output') for key,value in data['renders'].items()},
        'subjective_listening':data['subjective_listening']}


def task_status(task_file):
    """Small handoff/resume view; leave full design/transaction logs on disk."""
    task=_task(task_file);rows=[]
    for folder in (Path(task_file).parent/'candidates').iterdir():
        if not folder.is_dir(): continue
        path=folder/'candidate.json'
        if not path.exists():
            capture_file=folder/'capture.json'
            checked=read(capture_file) if capture_file.exists() else None
            phase=('capture_context_validated' if checked['parsed_context_diff']['equal'] and checked['complete_other_sound_states_equal'] else 'capture_rejected') if checked else 'preparing_or_interrupted'
            rows.append({'id':folder.name,'phase':phase,
                         'observations':str(capture_file if capture_file.exists() else folder),
                         'next_action':'Inspect the retained capture/context comparison, or the incomplete branch before continuing'})
            continue
        state=read(path);spec=state['request'];audio_path=folder/'audio/audition.json'
        audio=read(audio_path) if audio_path.exists() else None
        rows.append({'id':state['id'],'phase':state['phase'],'attempt':state['attempt'],'parent':spec.get('parent'),
                     'description':spec['description'],'mechanisms':spec['mechanisms'],
                     'artifact':state.get('artifact'),'message':state.get('message'),'request':str(path),
                     'observations':str(path),'complete_state_equal':state.get('complete_sound_state_equal_after_reopen'),
                     'audio_status':audio.get('status','in_progress') if audio else 'not_run',
                     'audio_observations':str(audio_path) if audio else None,
                     'audio':{key:audio['renders'].get(key,{}).get('output') for key in ('solo','context-1')} if audio else {},
                     'subjective_listening':state.get('subjective_listening','not_performed')})
    return {'task':str(Path(task_file).resolve()),'role':task['role'],'brief':task['brief'],
            'target':{key:task['target'][key] for key in ('index','iid','name','plugin')},
            'budget':task['budget']|{'used_candidates':len(rows)},'candidates':rows,
            'context':{'omitted':['full parameter/design/transaction records','signal analysis arrays','complete scores/context'],
                       'next_action':'Read only the relevant observation file, candidate --detail, audition --detail, or saved task phrase when needed; omitted means unknown'}}


def handoff_report(task_file,identifiers,output,recommended=None,rationale='',comparison=None,listening=None):
    """Index actual states/audio without repeating catalogs or analysis arrays."""
    task=_task(task_file)
    if not identifiers or len(set(identifiers))!=len(identifiers):
        raise ValueError('Choose distinct verified candidates for this handoff')
    if recommended and (recommended not in identifiers or not rationale.strip()):
        raise ValueError('A recommendation must name an included candidate and explain its musical rationale')
    listener=listening or {'status':'not_performed','who':None,'ability':'No listening supplied','method':'Signal analysis only'}
    if not isinstance(listener,dict) or listener.get('status') not in ('performed','not_performed'):
        raise ValueError('Listening metadata requires status performed or not_performed')
    if listener['status']=='performed' and not all(isinstance(listener.get(key),str) and listener[key].strip() for key in ('who','method')):
        raise ValueError('Performed listening requires who and method; this records caller evidence, not a CLI listening claim')
    rows=[]
    for identifier in identifiers:
        folder=_candidate_folder(task,identifier);report=read(folder/'candidate.json');audio=read(folder/'audio/audition.json')
        if report['phase']!='ready' or audio.get('status')!='verified':
            raise ValueError(f'{identifier} lacks verified native state/audio; finish candidate and audition first')
        doc,reopened=Project.read(report['artifact']),Project.read(folder/f'reopened-{report["attempt"]}.flp')
        channel=_target_index(task,doc)
        if state_view(doc,channel)!=state_view(reopened,_target_index(task,reopened)):
            raise ValueError(f'{identifier} complete sound state differs after reopening; no handoff published')
        spec=report['request'];track=doc.channels()[channel]['mixer_track']
        rows.append({'id':identifier,'description':spec['description'],'mechanisms':spec['mechanisms'],
                     'tradeoffs':spec.get('tradeoffs',[]),'parent':spec.get('parent'),
                     'project':report['artifact'],'cold_reopened_project':str(folder/f'reopened-{report["attempt"]}.flp'),
                     'solo':audio['renders']['solo']['output'],'context':audio['renders']['context-1']['output'],
                     'effects':{'track':track,'slots':doc.mixer()[track]['plugins']},
                     'identity':report['reopened']['identity'],'native_fl_version':doc.version,
                     'operations_and_resources':str(folder/'candidate.json'),'audio_evidence':str(folder/'audio/audition.json'),
                     'complete_state_equal_after_reopen':True,'audio_status':'verified'})
    if comparison:
        compared=read(comparison)
        if compared.get('kind')!='flstudio.sound-design.comparison':
            raise ValueError('Use comparison.json produced by sound-design compare for these candidates')
        found={row['id']:row for row in compared['candidates']}
        if any(row['id'] not in found or Path(found[row['id']]['artifact']).resolve()!=Path(row['project']).resolve() for row in rows):
            raise ValueError('Comparison must refer to these same task/candidate artifacts')
    result={'kind':'flstudio.sound-design.result','schema_version':1,'task_file':str(Path(task_file).resolve()),
            'role':task['role'],'brief':task['brief'],'target':{key:task['target'][key] for key in ('index','iid','name','plugin')},
            'candidates':rows,'recommended':recommended,'rationale':rationale,
            'recommendation_scope':'Caller-supplied choice; provisional unless actual listening is recorded',
            'comparison':str(Path(comparison).resolve()) if comparison else None,
            'listening':listener,'listening_evidence_source':'caller-supplied; the CLI does not listen',
            'known_resources':task['resources'],
            'unresolved':['Opaque plugin-internal dependencies require declared resources; see candidate evidence']+
                         (['Subjective sound quality and contextual preference'] if listener['status']=='not_performed' else []),
            'apply':f'sound-design apply --task "{Path(task_file).resolve()}" --candidate ID --project CURRENT.flp --output NEW.flp',
            'details_omitted':['full parameter catalogs','transaction histories','signal arrays','all score/context records']}
    write(Path(output),result,new=True)
    return result


def register(app,emit,json_option):
    import click
    from .contracts import Result
    @app.group('sound-design')
    @json_option
    def group():
        """Delegate actual-context plugin design with isolated native FL checkpoints."""
    @group.command('prepare')
    @click.option('--project',required=True,type=click.Path(path_type=Path))
    @click.option('--channel',required=True,type=click.IntRange(0))
    @click.option('--role',type=click.Choice(ROLES),default='other')
    @click.option('--brief',required=True)
    @click.option('--constraints',type=click.Path(path_type=Path))
    @click.option('--output-dir',required=True,type=click.Path(path_type=Path))
    @json_option
    def prepare_command(project,channel,role,brief,constraints,output_dir):
        data=prepare(project,channel,output_dir,brief,role,read(constraints) if constraints else None)
        emit(Result(command='sound-design prepare',status='artifact_ready',verified_scopes=['saved_sound_task'],
                    data={'task_file':data['task_file'],'role':role,'target':data['target'],'duration_seconds':data['duration_seconds'],'assumptions':data['assumptions'],'handoff':data['handoff']}))
    @group.command('candidate')
    @click.option('--task',required=True,type=click.Path(path_type=Path))
    @click.option('--request',required=True,type=click.Path(path_type=Path))
    @click.option('--fl-install',default=INSTALL,type=click.Path(path_type=Path))
    @click.option('--resume',is_flag=True)
    @click.option('--dry-run',is_flag=True)
    @click.option('--detail',is_flag=True,help='Include full transaction and checkpoint observations in this response.')
    @json_option
    def candidate_command(task,request,fl_install,resume,dry_run,detail):
        specification=read(request)
        if dry_run:
            task_data=_task(task)
            _candidate_folder(task_data,specification.get('id'))
            project=Project.read(task_data['context_project'])
            _edit(project,task_data['target']['index'],specification)
            emit(Result(command='sound-design candidate',status='planned',data={'request':specification,
                 'file_effects':[],'process_started':False,'host_params_validated':False,
                 'message':'Saved edits were checked in memory. Host names/values require an isolated actual candidate run.'}))
            return
        data=candidate(task,specification,fl_install,resume)
        emit(Result(command='sound-design candidate',status='artifact_ready' if data['phase']=='ready' else 'failed' if data['phase']=='failed' else 'unknown',
                    reason_code=None if data['phase']=='ready' else data.get('reason_code','candidate_not_confirmed'),
                    verified_scopes=['native_sound_checkpoint','reopened_host_parameter_values','reopened_complete_sound_state'] if data['phase']=='ready' else [],data=data if detail else _candidate_summary(data)))
        if data['phase']!='ready': raise click.exceptions.Exit(5)
    @group.command('audition')
    @click.option('--task',required=True,type=click.Path(path_type=Path))
    @click.option('--candidate','identifier',required=True)
    @click.option('--fl-install',default=INSTALL,type=click.Path(path_type=Path))
    @click.option('--repeats',default=2,type=click.IntRange(2,5))
    @click.option('--timeout',type=click.FloatRange(1,1800),help='Optional smaller per-render timeout, within the task budget.')
    @click.option('--detail',is_flag=True)
    @json_option
    def audition_command(task,identifier,fl_install,repeats,timeout,detail):
        data=audition(task,identifier,fl_install,repeats,timeout)
        emit(Result(command='sound-design audition',status=data['status'],reason_code=None if data['status']=='verified' else 'sound_audio_unconfirmed',
                    verified_scopes=['native_solo_context_audio','reopened_audio_proxies'] if data['status']=='verified' else [],data=data if detail else _audition_summary(data,_candidate_folder(_task(task),identifier))))
        if data['status']!='verified': raise click.exceptions.Exit(5)
    @group.command('compare')
    @click.option('--task',required=True,type=click.Path(path_type=Path))
    @click.option('--candidate','identifiers',required=True,multiple=True)
    @click.option('--output-dir',required=True,type=click.Path(path_type=Path))
    @json_option
    def compare_command(task,identifiers,output_dir):
        data=compare_candidates(task,identifiers,output_dir)
        emit(Result(command='sound-design compare',status='artifact_ready',verified_scopes=['level_matched_previews'],data=data))
    @group.command('apply')
    @click.option('--task',required=True,type=click.Path(path_type=Path))
    @click.option('--candidate','identifier',required=True)
    @click.option('--project',required=True,type=click.Path(path_type=Path))
    @click.option('--output',required=True,type=click.Path(path_type=Path))
    @click.option('--channel-only',is_flag=True)
    @click.option('--undo',is_flag=True)
    @json_option
    def apply_command(task,identifier,project,output,channel_only,undo):
        data=apply_candidate(task,identifier,project,output,not channel_only,undo)
        emit(Result(command='sound-design apply',status='artifact_ready',verified_scopes=['saved_complete_channel_state','score_preservation'],data=data))
    @group.command('status')
    @click.option('--task',required=True,type=click.Path(path_type=Path))
    @json_option
    def status_command(task):
        emit(Result(command='sound-design status',status='verified',verified_scopes=['saved_sound_task_summary'],data=task_status(task)))
    @group.command('support')
    @click.option('--project',required=True,type=click.Path(path_type=Path))
    @click.option('--channel',required=True,type=click.IntRange(0))
    @json_option
    def support_command(project,channel):
        emit(Result(command='sound-design support',status='verified',verified_scopes=['saved_plugin_identity'],data=support(project,channel)))
    @group.command('report')
    @click.option('--task',required=True,type=click.Path(path_type=Path))
    @click.option('--candidate','identifiers',required=True,multiple=True)
    @click.option('--output',required=True,type=click.Path(path_type=Path))
    @click.option('--recommended')
    @click.option('--rationale',default='')
    @click.option('--comparison',type=click.Path(path_type=Path))
    @click.option('--listening',type=click.Path(path_type=Path),help='Optional caller listening evidence JSON; the CLI does not listen.')
    @json_option
    def report_command(task,identifiers,output,recommended,rationale,comparison,listening):
        data=handoff_report(task,identifiers,output,recommended,rationale,comparison,read(listening) if listening else None)
        emit(Result(command='sound-design report',status='artifact_ready',verified_scopes=['saved_sound_handoff_index'],
                    data={'output':str(output.resolve()),'candidates':len(data['candidates']),'recommended':recommended,
                          'listening':data['listening'],'details_omitted':data['details_omitted']}))
    @group.command('capture')
    @click.option('--task',required=True,type=click.Path(path_type=Path))
    @click.option('--session',required=True,type=click.Path(path_type=Path))
    @click.option('--id','identifier',required=True)
    @click.option('--description',required=True)
    @click.option('--mechanism','mechanisms',multiple=True,required=True)
    @click.option('--fl-install',default=INSTALL,type=click.Path(path_type=Path))
    @click.option('--detail',is_flag=True)
    @json_option
    def capture_command(task,session,identifier,description,mechanisms,fl_install,detail):
        data=capture(task,session,identifier,description,mechanisms,fl_install)
        emit(Result(command='sound-design capture',status='artifact_ready' if data['phase']=='ready' else 'unknown',
                    verified_scopes=['native_sound_checkpoint'] if data['phase']=='ready' else [],data=data if detail else _candidate_summary(data)))
        if data['phase']!='ready': raise click.exceptions.Exit(5)
    @group.command('knowledge')
    @click.option('--search',default='')
    @click.option('--id','identifier')
    @json_option
    def knowledge_command(search,identifier):
        emit(Result(command='sound-design knowledge',status='verified',verified_scopes=['source_attributed_knowledge'],data=knowledge(search,identifier)))

    sytrus_group=app.commands['sytrus']
    @sytrus_group.command('design-inspect')
    @click.option('--project',required=True,type=click.Path(path_type=Path))
    @click.option('--channel',required=True,type=click.IntRange(0))
    @click.option('--operator','operators',multiple=True,type=click.IntRange(1,6),help='Expand only these operators; other operators remain omitted.')
    @click.option('--summary',is_flag=True,help='Omit raw envelope point records; keep exposed semantic controls.')
    @json_option
    def design_inspect(project,channel,operators,summary):
        from .sytrus_design import inspect_design
        data=inspect_design(Project.read(project),channel);omitted=[]
        if operators:
            data['operators']=[row for row in data['operators'] if row['operator'] in operators]
            omitted.extend(f'operator {n}' for n in range(1,7) if n not in operators)
        if summary:
            for row in data['operators']: row.pop('volume_envelope_points',None)
            omitted.append('raw envelope point records')
        if omitted:data['context']={'omitted':omitted,'meaning':'Omitted fields are unknown here; expand only the next relevant operator/detail'}
        emit(Result(command='sytrus design-inspect',status='verified',verified_scopes=['saved_sytrus_design_fields'],data=data))
    @sytrus_group.command('design-edit')
    @click.option('--project',required=True,type=click.Path(path_type=Path))
    @click.option('--channel',required=True,type=click.IntRange(0))
    @click.option('--request',required=True,type=click.Path(path_type=Path))
    @click.option('--output',required=True,type=click.Path(path_type=Path))
    @click.option('--dry-run',is_flag=True)
    @json_option
    def design_edit(project,channel,request,output,dry_run):
        from .sytrus_design import apply_design,inspect_design
        doc=Project.read(project)
        data=apply_design(doc,channel,read(request))
        if dry_run:
            emit(Result(command='sytrus design-edit',status='planned',data={'after':data['after'],'file_effects':[],'process_started':False})); return
        doc.save(output)
        if not _design_equal(inspect_design(doc,channel),inspect_design(Project.read(output),channel)):
            raise ValueError('Saved Sytrus design readback differs')
        emit(Result(command='sytrus design-edit',status='artifact_ready',verified_scopes=['saved_sytrus_design_fields'],data={'output':str(output.resolve()),'design':data,'native_reopen_verified':False,'next_action':'Use sound-design candidate/audition for actual FL loading and sound evidence'}))
