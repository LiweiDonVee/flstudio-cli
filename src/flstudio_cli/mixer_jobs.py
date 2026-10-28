"""Native Mixer expansion with saved identity, routing and opaque-state checks."""
from __future__ import annotations

import json
from pathlib import Path


def prepare(session, count, job):
    from .live import Bridge
    from .sessions import save
    from .owned_ui import observe
    from .json_output import canonical_json
    if job.exists() or not job.parent.is_dir(): raise ValueError('Choose a new job file with an existing parent')
    if session.get('desktop_mode') != 'private': raise ValueError('Mixer expansion requires a private owned session')
    bridge = Bridge(session=session)
    if bridge.call('get_play_state') != {'playing': False, 'recording': False}:
        raise ValueError('Stop and disarm before expanding Mixer')
    def api(module, function, *args):
        return bridge.call('cli_api_call', {'module': module, 'function': function, 'args': list(args)})['value']
    original_count = api('mixer', 'getTrackCount')
    if count <= original_count: raise ValueError('Choose a larger ordinary insert count')
    baseline = job.with_suffix('.before.flp')
    save(session, baseline)
    api('mixer', 'setTrackNumber', original_count)
    api('ui', 'showWindow', 0); api('ui', 'setFocused', 0)
    api('transport', 'globalTransport', 90, 1)
    menus = [w for w in observe(session)['windows'] if w['class'] == 'TQuickPopupMenuWindow' and w['visible']]
    if len(menus) != 1: raise ValueError('Expected one Mixer menu; inspect the owned windows')
    frame = observe(session, job.with_suffix('.menu.bmp'), menus[0]['hwnd'])
    receipt = job.with_suffix('.menu.json'); receipt.write_text(canonical_json(frame), encoding='utf-8')
    data = {'session': session, 'before_count': original_count, 'desired_count': count,
            'before_project': str(baseline.resolve()), 'menu_observation': str(receipt.resolve())}
    job.write_text(canonical_json(data), encoding='utf-8')
    return {k: v for k, v in {**data, 'job': str(job.resolve()), 'native_change_verified': False,
            'next': 'Append the requested tracks through the observed Mixer UI, keeping existing indices; then verify-expand.'}
            .items() if k != 'session'}


def verify(job, output):
    from .live import Bridge
    from .sessions import save
    from .flp import Project
    data = json.loads(job.read_text(encoding='utf-8'))
    current = Bridge(session=data['session']).call('cli_api_call', {'module': 'mixer', 'function': 'getTrackCount'})['value']
    if current != data['desired_count']:
        return {'status': 'unknown', 'reason_code': 'mixer_count_not_reached', 'actual_count': current,
                'desired_count': data['desired_count'], 'verified_scopes': [], 'file_effects': []}
    save(data['session'], output)
    before, after = Project.read(data['before_project']), Project.read(output)
    left, right = before.mixer()[:-1], after.mixer()[:-1]
    def public(track):
        return {**track, 'plugins': [{k: v for k, v in p.items() if k != 'state_sha256'} for p in track['plugins']]}
    unchanged, mismatches = True, []
    for a, b in zip(left, right):
        same = public(a) == public(b)
        for plugin in a['plugins']:
            try: same = same and before._effect_state(a['index'], plugin['slot'])[1].data == after._effect_state(a['index'], plugin['slot'])[1].data
            except ValueError: same = False
        if not same: mismatches.append(a['index']); unchanged = False
    routing = [(c['iid'], c['mixer_track']) for c in before.channels()] == [(c['iid'], c['mixer_track']) for c in after.channels()]
    links = [e.data for e in before.events if e.id in (223, 227)] == [e.data for e in after.events if e.id in (223, 227)]
    count_ok = len(right) - 1 == data['desired_count']
    confirmed = count_ok and unchanged and routing and links
    return {'status': 'verified' if confirmed else 'unknown', 'reason_code': None if confirmed else 'mixer_identity_not_confirmed',
            'verified_scopes': ['native_mixer_expansion', 'existing_mixer_state', 'channel_routing', 'controller_links'] if confirmed else [],
            'output': str(output.resolve()), 'before_count': data['before_count'], 'actual_count': len(right) - 1,
            'existing_tracks_unchanged': unchanged, 'changed_old_tracks': mismatches, 'channel_routing_unchanged': routing,
            'controller_links_unchanged': links}


def register(app, emit, json_option):
    import click
    from .contracts import Result
    from .json_output import decode_json
    @app.group('mixer')
    @json_option
    def group():
        """Prepare native track expansion and verify the saved result."""
    @group.command('prepare-expand')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @click.option('--count', required=True, type=click.IntRange(1, 500))
    @click.option('--job', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def prepared(session, count, job, dry_run):
        if dry_run:
            emit(Result(command='mixer prepare-expand', status='planned', data={'desired_count': count,
                'file_effects': [], 'bridge_contacted': False})); return
        emit(Result(command='mixer prepare-expand', status='partial', reason_code='native_ui_expansion_required',
                    data=prepare(decode_json(session.read_text(encoding='utf-8-sig')), count, job)))
    @group.command('verify-expand')
    @click.option('--job', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @json_option
    def verified(job, output):
        data = verify(job, output)
        emit(Result(command='mixer verify-expand', status=data['status'], reason_code=data['reason_code'],
                    verified_scopes=data['verified_scopes'], data=data))
        if data['status'] != 'verified': raise click.exceptions.Exit(5)
