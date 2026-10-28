"""Fixed Piano Roll dispatcher with actual score receipts and native target audits."""
from __future__ import annotations

import json
import math
from pathlib import Path
import uuid


FIELDS = ('number', 'time', 'length', 'velocity', 'pan', 'release', 'color', 'pitchofs',
          'slide', 'porta', 'muted', 'repeats', 'fcut', 'fres', 'group', 'selected')
SCRIPT = '''"""FL Studio CLI score dispatcher. Run this named script, without preview."""
import json
import os
import flpianoroll as flp
PREFIX = %r
PID = %d
OWNER = %r
FIELDS = %r
def read():
    return [{k:getattr(flp.score.getNote(i),k) for k in FIELDS} for i in range(flp.score.noteCount)]
with open(PREFIX + '.request.json', 'r') as stream:
    request = json.loads(stream.read())
if os.getpid() != PID or request['owner_marker'] != OWNER or request['expected_pid'] != PID:
    raise ValueError('CLI score instance mismatch')
try:
    with open(PREFIX + '.response.json', 'r') as stream:
        previous = json.loads(stream.read())
except FileNotFoundError:
    previous = None
if previous and previous['request_id'] == request['request_id']:
    raise ValueError('This score request has already executed; read its receipt')
before = read()
response = {'request_id':request['request_id'], 'owner_marker':OWNER, 'pid':PID,
    'ppq':flp.score.PPQ, 'requested_target':request['target'], 'target_independently_observed':False,
    'operation':request['operation'], 'before':before, 'after':None, 'status':'failed'}
try:
    if request['operation'] in ('replace','edit'):
        if before != request['expected_before']:
            raise ValueError('Active score no longer matches the previous read receipt')
        original = [flp.score.getNote(i).clone() for i in range(flp.score.noteCount)]
        planned = [] if request['operation'] == 'replace' else [n.clone() for n in original]
        if request['operation'] == 'edit':
            for patch in request['edit']['patch']:
                for key,value in patch['set'].items(): setattr(planned[patch['index']],key,value)
            planned = [n for i,n in enumerate(planned) if i not in request['edit']['delete']]
        for spec in request.get('notes', request.get('edit',{}).get('append',[])):
            note = flp.Note()
            for key,value in spec.items():
                setattr(note,key,value)
            planned.append(note)
        response['canonical_notes'] = [{k:getattr(n,k) for k in FIELDS} for n in planned]
        try:
            flp.score.clearNotes(True)
            for note in planned: flp.score.addNote(note)
        except Exception:
            flp.score.clearNotes(True)
            for note in original: flp.score.addNote(note)
            response['restored'] = read() == before
            raise
    elif request['operation'] != 'read':
        raise ValueError('Unsupported score operation')
    response['after'] = read()
    response['status'] = 'observed'
except Exception as error:
    response['error'] = str(error)
    response['after'] = read()
with open(PREFIX + '.response.json', 'w') as stream:
    stream.write(json.dumps(response,allow_nan=False))
'''


def prepare(session):
    from .owned_ui import _binding
    _binding(session)
    if session.get('desktop_mode') != 'private': raise ValueError('Live score jobs require an owned private session')
    root = Path.home() / 'Documents/Image-Line/FL Studio/Settings/Piano roll scripts'
    root.mkdir(parents=True, exist_ok=True)
    prefix = 'FLCLI_' + uuid.UUID(session['owner_marker'].split(':')[1]).hex[:12]
    path = root / (prefix + '.pyscript')
    source = SCRIPT % (prefix, session['pid'], session['owner_marker'], FIELDS)
    if path.exists() and path.read_text(encoding='utf-8') != source:
        raise ValueError('Installed dispatcher differs; start a new owned session instead of rewriting a cached script')
    if not path.exists(): path.write_text(source, encoding='utf-8')
    return {'script': str(path), 'script_menu_name': prefix, 'request': str(root / (prefix + '.request.json')),
            'response': str(root / (prefix + '.response.json'))}


def cleanup(session):
    """Remove this worker's generated dispatcher; preserve edited/older sources."""
    root = Path.home() / 'Documents/Image-Line/FL Studio/Settings/Piano roll scripts'
    prefix = 'FLCLI_' + uuid.UUID(session['owner_marker'].split(':')[1]).hex[:12]
    script = root / (prefix + '.pyscript')
    if not script.exists(): return {'removed': []}
    source = SCRIPT % (prefix, session['pid'], session['owner_marker'], FIELDS)
    if script.read_text(encoding='utf-8') != source: return {'removed': [], 'preserved_changed_dispatcher': str(script)}
    removed, retained = [], []
    for name in (prefix + '.pyscript', prefix + '.request.json', prefix + '.response.json'):
        path = root / name
        try:
            if path.is_file(): path.unlink(); removed.append(str(path))
        except OSError as error:
            retained.append({'path': str(path), 'error': str(error)})
    return {'removed': removed, 'retained': retained}


def validate_notes(notes, partial=False):
    if not isinstance(notes, list): raise ValueError('Notes must be an array')
    integer_ranges = {'number': (0, 131), 'time': (0, 0x7fffffff), 'length': (1, 0x7fffffff),
                      'color': (0, 15), 'pitchofs': (-120, 120), 'repeats': (0, 14), 'group': (0, 65535)}
    for note in notes:
        if (not isinstance(note, dict) or set(note) - set(FIELDS) or not note or
                (not partial and not {'number', 'time', 'length'} <= set(note))):
            raise ValueError('Each live note requires number/time/length and supported Piano Roll properties')
        for field, value in note.items():
            if field in integer_ranges:
                low, high = integer_ranges[field]
                if type(value) is not int or not low <= value <= high: raise ValueError('Invalid note ' + field)
            elif field in ('slide', 'porta', 'muted', 'selected'):
                if type(value) is not bool: raise ValueError(field + ' must be boolean')
            elif type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(field + ' must be finite 0..1')
    return notes


def validate_edit(edit, count):
    if not isinstance(edit, dict) or set(edit) - {'patch', 'delete', 'append'}:
        raise ValueError('Score edit accepts patch, delete, append arrays')
    edit = {'patch': [], 'delete': [], 'append': [], **edit}
    if any(not isinstance(edit[k], list) for k in edit): raise ValueError('Score edit fields must be arrays')
    changed = set()
    for patch in edit['patch']:
        if not isinstance(patch, dict) or set(patch) != {'index', 'set'}: raise ValueError('Patch requires index and set')
        index = patch['index']
        if type(index) is not int or not 0 <= index < count or index in changed: raise ValueError('Patch index is absent or duplicated')
        validate_notes([patch['set']], partial=True); changed.add(index)
    deleted = set()
    for index in edit['delete']:
        if type(index) is not int or not 0 <= index < count or index in deleted or index in changed:
            raise ValueError('Delete index is absent, duplicated, or also patched')
        deleted.add(index)
    validate_notes(edit['append'])
    return edit


def queue(session, target, job, notes=None, read_job=None, edit=None):
    from .json_output import canonical_json
    from .live import Bridge
    from .sessions import save
    from .flp import Project
    from .owned_ui import observe, submit_key
    if job.exists() or not job.parent.is_dir(): raise ValueError('Choose a new job file with an existing parent')
    if set(target) != {'channel', 'pattern'} or any(type(v) is not int for v in target.values()) or target['channel'] < 0 or target['pattern'] < 1:
        raise ValueError('Target requires global channel>=0 and pattern>=1')
    paths = prepare(session)
    request_file, response_file = Path(paths['request']), Path(paths['response'])
    if request_file.exists():
        previous = json.loads(request_file.read_text(encoding='utf-8'))
        receipt = json.loads(response_file.read_text(encoding='utf-8')) if response_file.exists() else {}
        if receipt.get('request_id') != previous['request_id']:
            raise ValueError('A score request is still pending; inspect its job before queuing another')
    bridge = Bridge(session=session)
    play = bridge.call('get_play_state')
    if play['playing'] or play['recording']: raise ValueError('Stop playback/recording before a score job')
    if notes is not None and edit is not None: raise ValueError('Choose notes replacement or edit')
    request = {'request_id': uuid.uuid4().hex, 'expected_pid': session['pid'], 'owner_marker': session['owner_marker'],
               'operation': 'edit' if edit is not None else 'read' if notes is None else 'replace', 'target': target}
    if notes is not None or edit is not None:
        if notes is not None: validate_notes(notes)
        prior = json.loads(Path(read_job).read_text(encoding='utf-8')) if read_job else None
        if (not prior or prior['session']['controller_instance'] != session['controller_instance'] or prior['request']['target'] != target
                or prior.get('result', {}).get('status') != 'verified'):
            raise ValueError('Replace requires a completed read job for this exact session and target')
        request['expected_before'] = prior['result']['receipt']['after']
        if edit is not None: request['edit'] = validate_edit(edit, len(request['expected_before']))
        else: request['notes'] = notes
    checkpoint = job.with_suffix('.before.flp')
    save(session, checkpoint)
    native = Project.read(checkpoint)
    if target['pattern'] not in native.patterns() or target['channel'] >= len(native.channels()):
        raise ValueError('Choose an existing pattern and global channel')
    def api(module, function, *args):
        return bridge.call('cli_api_call', {'module': module, 'function': function, 'args': list(args)})['value']
    api('patterns', 'jumpToPattern', target['pattern'])
    api('channels', 'selectOneChannel', target['channel'], True)
    api('ui', 'showWindow', 1)
    api('ui', 'setFocused', 1)
    if api('patterns', 'patternNumber') != target['pattern'] or api('channels', 'selectedChannel', 0, False, True) != target['channel']:
        raise ValueError('FL did not select the requested channel and pattern')
    racks = [w for w in observe(session, children=True)['windows'] if w['visible'] and w['class'] == 'TStepSeqForm']
    if len(racks) != 1: raise ValueError('Expected one visible owned Channel Rack')
    frame = observe(session, job.with_suffix('.rack.bmp'), racks[0]['hwnd'])
    submit_key(session, frame, 'f7')
    if api('ui', 'getFocusedFormID') != 3: raise ValueError('FL did not open the selected channel Piano Roll')
    data = {'session': session, 'request': request, 'paths': paths, 'before_project': str(checkpoint.resolve()),
            'target_open_method': 'selected_global_channel_rack_f7', 'rack_observation': frame}
    job.write_text(canonical_json(data), encoding='utf-8')
    request_file.write_text(canonical_json(request), encoding='utf-8')
    return {'job': str(job.resolve()), 'script_menu_name': paths['script_menu_name'], 'target': target,
            'operation': request['operation'], 'script_executed': False,
            'target_opened_via_channel_rack': True, 'next': 'Run this named script in the opened Piano Roll; then collect the job.'}


def collect(job):
    from .flp import Project
    from .json_output import canonical_json
    from .sessions import save
    data = json.loads(job.read_text(encoding='utf-8'))
    if 'result' in data: return data['result']
    path = Path(data['paths']['response'])
    if not path.exists(): return {'status': 'unknown', 'reason_code': 'score_receipt_pending', 'script_executed': None}
    receipt = json.loads(path.read_text(encoding='utf-8'))
    request, session = data['request'], data['session']
    if (receipt.get('request_id') != request['request_id'] or receipt.get('pid') != session['pid'] or receipt.get('owner_marker') != session['owner_marker']):
        return {'status': 'unknown', 'reason_code': 'score_receipt_pending', 'script_executed': None}
    result = {'status': 'failed', 'reason_code': 'score_script_failed', 'receipt': receipt, 'verified_scopes': []}
    if receipt['status'] == 'observed':
        after_path = job.with_suffix('.after.flp')
        save(session, after_path)
        before, after = Project.read(data['before_project']), Project.read(after_path)
        target = request['target']
        def scope(project, selected):
            return sorted([json.dumps({'pattern': number, **note}, sort_keys=True) for number, pattern in project.patterns().items()
                for note in pattern['notes'] if ((number == target['pattern'] and note['channel_index'] == target['channel']) == selected)])
        native = [n for n in after.patterns().get(target['pattern'], {}).get('notes', []) if n['channel_index'] == target['channel']]
        live_core = sorted((n['number'], n['time'], n['length'], round(n['velocity'] * 128)) for n in receipt['after'])
        native_core = sorted((n['key'], n['start_tick'], n['length_tick'], n['velocity']) for n in native)
        native_properties = [{'number': n['key'], 'time': n['start_tick'], 'length': n['length_tick'],
            'velocity': n['velocity'] / 128, 'pan': n['pan'] / 128, 'release': n['release'] / 128,
            'color': n['midi_channel'] & 15, 'pitchofs': n['fine_pitch'] - 120, 'slide': bool(n['flags'] & 8),
            'porta': bool(n['midi_channel'] & 16), 'muted': bool(n['midi_channel'] & 32),
            'selected': bool(n['midi_channel'] & 128), 'repeats': n['reserved_raw'] & 15,
            'fcut': n['mod_x'] / 255, 'fres': n['mod_y'] / 255, 'group': n['group']} for n in native]
        def same_notes(left, right):
            order = lambda n: tuple(n[k] for k in FIELDS)
            return len(left) == len(right) and all(all(
                math.isclose(a[k], b[k], abs_tol=.000001) for k in FIELDS)
                for a, b in zip(sorted(left, key=order), sorted(right, key=order)))
        properties_match = same_notes(receipt['after'], native_properties)
        others_unchanged = scope(before, False) == scope(after, False)
        matches = live_core == native_core and properties_match and others_unchanged
        if request['operation'] != 'read':
            matches = matches and same_notes(receipt['canonical_notes'], receipt['after'])
        result.update(status='verified' if matches else 'unknown', reason_code=None if matches else 'score_target_or_value_not_confirmed',
            native_project=str(after_path.resolve()), target_core_verified=live_core == native_core,
            target_properties_verified=properties_match,
            other_scores_unchanged=others_unchanged, native_target_notes=native,
            verified_scopes=['live_score_readback', 'native_score_target_properties', 'other_scores_unchanged'] if matches else [])
    data['result'] = result
    job.write_text(canonical_json(data), encoding='utf-8')
    return result


def register(app, emit, json_option):
    import click
    from .contracts import Result
    from .json_output import decode_json
    @app.group('piano-roll')
    @json_option
    def group():
        """Live score jobs with named-script execution and native target checks."""
    @group.command('queue')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @click.option('--channel', required=True, type=click.IntRange(0))
    @click.option('--pattern', required=True, type=click.IntRange(1, 999))
    @click.option('--job', required=True, type=click.Path(path_type=Path))
    @click.option('--notes', type=click.Path(path_type=Path), help='Omit to read; provide a full note array to replace.')
    @click.option('--edit', type=click.Path(path_type=Path), help='Patch/delete existing note indices and append new notes, preserving untouched properties.')
    @click.option('--read-job', type=click.Path(path_type=Path), help='Completed previous read job, required for a replacement.')
    @click.option('--dry-run', is_flag=True)
    @json_option
    def queued(session, channel, pattern, job, notes, edit, read_job, dry_run):
        desired = validate_notes(decode_json(notes.read_text(encoding='utf-8-sig'))) if notes else None
        changes = decode_json(edit.read_text(encoding='utf-8-sig')) if edit else None
        if notes and edit: raise ValueError('Choose notes replacement or edit')
        if dry_run:
            emit(Result(command='piano-roll queue', status='planned', data={'target': {'channel': channel, 'pattern': pattern},
                'script_executed': False, 'file_effects': [], 'bridge_contacted': False})); return
        data = queue(decode_json(session.read_text(encoding='utf-8-sig')), {'channel': channel, 'pattern': pattern}, job, desired, read_job, changes)
        emit(Result(command='piano-roll queue', status='partial', reason_code='named_script_execution_required', data=data))
    @group.command('result')
    @click.option('--job', required=True, type=click.Path(path_type=Path))
    @json_option
    def result(job):
        data = collect(job)
        emit(Result(command='piano-roll result', status=data['status'], reason_code=data.get('reason_code'),
                    verified_scopes=data.get('verified_scopes', []), data=data))
        if data['status'] != 'verified': raise click.exceptions.Exit(5)
