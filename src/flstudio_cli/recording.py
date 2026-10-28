"""Owned native recording jobs; schedule acknowledgement is not event evidence."""
from __future__ import annotations

import json
import math
from pathlib import Path
import uuid


def prepare(session, pattern, job):
    from .live import Bridge
    from .sessions import save
    from .json_output import canonical_json
    if job.exists() or not job.parent.is_dir(): raise ValueError('Choose a new job file with an existing parent')
    bridge = Bridge(session=session)
    if not bridge.call('cli_capabilities').get('recording_jobs'): raise ValueError('This owned controller does not support recording jobs')
    if bridge.call('get_play_state') != {'playing': False, 'recording': False}:
        raise ValueError('Stop and disarm before preparing recording')
    checkpoint = job.with_suffix('.before.flp')
    save(session, checkpoint)
    data = {'id': uuid.uuid4().hex, 'session': session, 'pattern_number': pattern,
            'before_project': str(checkpoint.resolve())}
    job.write_text(canonical_json(data), encoding='utf-8')
    return bridge.call('cli_record_prepare', {'id': data['id'], 'pattern_number': pattern})


def start(job, request):
    from .live import Bridge
    from .automation import target_address
    from .flp import Project
    from .json_output import canonical_json
    data = json.loads(job.read_text(encoding='utf-8'))
    if not isinstance(request, dict) or set(request) != {'clock', 'points', 'stop_at'} or not isinstance(request['points'], list):
        raise ValueError('Recording spec requires clock, points and stop_at')
    native = Project.read(data['before_project'])
    points = []
    for point in request['points']:
        if not isinstance(point, dict) or set(point) != {'at', 'target', 'value'}:
            raise ValueError('Each recording point requires at, target and value')
        points.append({**point, 'event_id': target_address(native, point['target'])})
    plan = {**request, 'points': points}
    data['request'] = plan
    job.write_text(canonical_json(data), encoding='utf-8')
    return Bridge(session=data['session']).call('cli_record_start', {'id': data['id'], **plan})


def status(job, cancel=False):
    from .live import Bridge
    data = json.loads(job.read_text(encoding='utf-8'))
    bridge = Bridge(session=data['session'])
    first = bridge.call('cli_record_cancel' if cancel else 'cli_record_status', {'id': data['id']})
    following = first['next_start']
    while following is not None:
        page = bridge.call('cli_record_status', {'id': data['id'], 'start': following})
        first['observations'].extend(page['observations']); following = page['next_start']
    first['next_start'] = None
    return first


def verify(job):
    from .fields import pattern_controllers
    from .flp import Project
    from .json_output import canonical_json
    from .sessions import save
    data = json.loads(job.read_text(encoding='utf-8'))
    if 'verification' in data: return data['verification']
    observed = status(job)
    if observed['phase'] not in ('completed', 'cancelled', 'failed') or observed['playing'] or observed['recording']:
        return {'status': 'unknown', 'reason_code': 'recording_not_finished', 'job': observed, 'verified_scopes': []}
    output = job.with_suffix('.after.flp')
    save(data['session'], output)
    before, after = Project.read(data['before_project']), Project.read(output)
    def records(project):
        return next((r['records'] for r in pattern_controllers(project) if r['pattern_number'] == data['pattern_number']), [])
    previous, recorded = records(before), records(after)
    from collections import Counter
    counts = Counter((r['position_raw'], r['target_address'], r['value_raw']) for r in previous)
    new_records = []
    for record in recorded:
        key = (record['position_raw'], record['target_address'], record['value_raw'])
        if counts[key]: counts[key] -= 1
        else: new_records.append(record)
    rows = []
    for point in observed['observations']:
        raw = int(point['raw_value']) & 0xffffffff
        matches = [r for r in new_records if r['target_address'] == point['event_id'] and r['value_raw'] == raw]
        rows.append({'point': point, 'native_matches': matches, 'recorded': bool(matches),
                     'host_value_matches_requested': math.isclose(point['observed_value'], point['value'], abs_tol=.0001),
                     'runtime_address_matches_saved': point['live_event_id'] == point['event_id']})
    changed = previous != recorded
    complete = observed['phase'] == 'completed' and bool(rows) and changed and all(
        r['recorded'] and r['host_value_matches_requested'] for r in rows)
    result = {'status': 'verified' if complete else 'partial' if changed else 'unknown',
        'reason_code': None if complete else 'partial_recording' if changed else 'recording_not_observed',
        'verified_scopes': ['native_pattern_recording'] if complete else ['native_pattern_events_observed'] if changed else [],
        'recorded_kind': 'pattern_events', 'pattern_number': data['pattern_number'], 'native_project': str(output.resolve()),
        'job': observed, 'before_records': previous, 'recorded_events': recorded, 'points': rows,
        'new_or_changed_events': new_records, 'timing_accuracy_verified': False,
        'verification_scope': 'native_pattern_event_data', 'canonical_plugin_values_verified': False,
        'recorded_count_is_not_scheduled_count': True}
    data['verification'] = result
    job.write_text(canonical_json(data), encoding='utf-8')
    return result


def register(app, emit, json_option):
    import click
    from .contracts import Result
    from .json_output import decode_json
    @app.group('recording')
    @json_option
    def group():
        """Record actual Pattern events in a private FL worker."""
    @group.command('prepare')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @click.option('--pattern', required=True, type=click.IntRange(1, 999))
    @click.option('--job', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def prepared(session, pattern, job, dry_run):
        if dry_run:
            emit(Result(command='recording prepare', status='planned', data={'pattern_number': pattern, 'submitted': False,
                'file_effects': [], 'bridge_contacted': False})); return
        data = prepare(decode_json(session.read_text(encoding='utf-8-sig')), pattern, job)
        emit(Result(command='recording prepare', status='partial', reason_code='confirm_recording_setup', data=data))
    @group.command('start')
    @click.option('--job', required=True, type=click.Path(path_type=Path))
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def started(job, request, dry_run):
        spec = decode_json(request.read_text(encoding='utf-8-sig'))
        if dry_run:
            emit(Result(command='recording start', status='planned', data={'spec': spec, 'submitted': False,
                'file_effects': [], 'bridge_contacted': False})); return
        emit(Result(command='recording start', status='partial', reason_code='recording_scheduled', data=start(job, spec)))
    def reader(name, function):
        @group.command(name)
        @click.option('--job', required=True, type=click.Path(path_type=Path))
        @json_option
        def read(job):
            data = function(job)
            emit(Result(command='recording ' + name, status='verified', verified_scopes=['recording_job_state'], data=data))
    reader('status', status)
    reader('cancel', lambda job: status(job, True))
    @group.command('verify')
    @click.option('--job', required=True, type=click.Path(path_type=Path))
    @json_option
    def verified(job):
        data = verify(job)
        emit(Result(command='recording verify', status=data['status'], reason_code=data['reason_code'],
                    verified_scopes=data['verified_scopes'], data=data))
        if data['status'] != 'verified': raise click.exceptions.Exit(5)
