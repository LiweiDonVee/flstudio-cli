"""Owned FL workers: explicit process identity and addressed MIDI sessions."""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
from contextlib import contextmanager
from pathlib import Path
import subprocess
import time
import uuid


def process_stamp(pid):
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.GetProcessTimes.argtypes = [w.HANDLE, c.POINTER(w.FILETIME), c.POINTER(w.FILETIME), c.POINTER(w.FILETIME), c.POINTER(w.FILETIME)]
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        code = w.DWORD()
        if not kernel.GetExitCodeProcess(handle, c.byref(code)):
            raise c.WinError(c.get_last_error())
        if code.value != 259:
            return None
        created, exited, system, user = w.FILETIME(), w.FILETIME(), w.FILETIME(), w.FILETIME()
        if not kernel.GetProcessTimes(handle, c.byref(created), c.byref(exited), c.byref(system), c.byref(user)):
            raise c.WinError(c.get_last_error())
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def start_worker(executable, project, folder, rpc_root, rpc_prefix, desktop_mode='private'):
    from .native import Startup, ProcessInfo, environment_block
    kernel, user = c.WinDLL('kernel32', use_last_error=True), c.WinDLL('user32', use_last_error=True)
    user.CreateDesktopW.argtypes = [w.LPCWSTR, w.LPCWSTR, c.c_void_p, w.DWORD, w.DWORD, c.c_void_p]
    user.CreateDesktopW.restype = w.HANDLE
    user.CloseDesktop.argtypes = [w.HANDLE]
    kernel.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL,
                                     w.DWORD, c.c_void_p, w.LPCWSTR, c.POINTER(Startup), c.POINTER(ProcessInfo)]
    kernel.CreateProcessW.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    name = 'flstudio_cli_owned_' + uuid.uuid4().hex if desktop_mode == 'private' else 'interactive'
    desktop = user.CreateDesktopW(name, None, None, 0, 0x01ff, None) if desktop_mode == 'private' else None
    if desktop_mode == 'private' and not desktop:
        raise c.WinError(c.get_last_error())
    setup, process = Startup(), ProcessInfo()
    setup.cb, setup.desktop, setup.flags, setup.show = c.sizeof(setup), name if desktop else None, 1, 1 if desktop_mode == 'interactive' else 0
    command = c.create_unicode_buffer(subprocess.list2cmdline([str(executable.resolve()), str(project.resolve())]))
    block = environment_block({'FLSTUDIO_CLI_SESSION_DIR': str(rpc_root.resolve()), 'FLSTUDIO_CLI_SESSION_TOKEN': rpc_prefix})
    try:
        if not kernel.CreateProcessW(str(executable.resolve()), command, None, None, False, 0x400, c.cast(block, c.c_void_p),
                                    str(executable.resolve().parent), c.byref(setup), c.byref(process)):
            raise c.WinError(c.get_last_error())
        # Keep the desktop alive until FL has attached its GUI thread and the
        # addressed controller has answered. Closing it immediately races FL's
        # asynchronous startup.
        yield {'pid': process.pid, 'process_created': process_stamp(process.pid), 'desktop': name}
    finally:
        if process.thread: kernel.CloseHandle(process.thread)
        if process.process: kernel.CloseHandle(process.process)
        if desktop: user.CloseDesktop(desktop)


def stop_worker(session):
    from .piano_roll import cleanup
    if not session.get('owner_marker', '').startswith('__FLCLI_OWNED__:'):
        raise ValueError('Session does not identify an owned worker')
    stamp = process_stamp(session['pid'])
    if stamp is None:
        return {'stopped': True, 'already_exited': True, 'piano_dispatcher': cleanup(session)}
    if stamp != session['process_created']:
        raise ValueError('PID was reused; refusing to stop another process')
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x00100001, False, session['pid'])
    if not handle:
        raise c.WinError(c.get_last_error())
    try:
        if not kernel.TerminateProcess(handle, 0):
            raise c.WinError(c.get_last_error())
        kernel.WaitForSingleObject(handle, 5000)
        stopped = process_stamp(session['pid']) is None
        return {'stopped': stopped, 'pid': session['pid'], 'piano_dispatcher': cleanup(session) if stopped else None}
    finally:
        kernel.CloseHandle(handle)


def start(source, output, install, port=9787, controller_dir=None, desktop_mode='private'):
    from .flp import Project
    from .json_output import canonical_json, decode_json
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Choose a new session directory with an existing parent')
    if desktop_mode not in ('private', 'interactive'): raise ValueError('Choose private or interactive desktop')
    if desktop_mode == 'interactive':
        import csv
        running = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq FL64.exe', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if any(row and row[0].casefold() == 'fl64.exe' for row in csv.reader(running.stdout.splitlines())):
            raise ValueError('Interactive launch requires other FL instances to be closed: FL has no verified force-new-instance flag. Use private mode to keep an editor open.')
    doc = Project.read(source)
    marker = '__FLCLI_OWNED__:' + uuid.uuid4().hex
    rpc_root = controller_dir or Path.home() / 'Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP'
    if not (rpc_root / 'flstudio_cli_extension.py').is_file():
        raise ValueError('Install the CLI controller extension first, or specify --controller-dir')
    rpc_prefix = marker.split(':')[1] + '-'
    if doc.channels():
        first_name = doc.channels()[0]['name']
        owner_field, original_title = 'first_channel', None
        doc.set_channel(0, {'name': marker})
    else:
        from .fields import metadata, set_metadata
        first_name, owner_field = None, 'title'
        original_title = metadata(doc)['title']
        set_metadata(doc, {'title': marker})
    output.mkdir()
    project = doc.save(output / 'project.flp')
    with start_worker(install / 'FL64.exe', project, output, rpc_root, rpc_prefix, desktop_mode) as worker:
        session = {**worker, 'owner_marker': marker,
                   'project': str(project), 'source': str(source.resolve()), 'first_channel_name': first_name,
                   'owner_field': owner_field, 'original_title': original_title,
                   'desktop_mode': desktop_mode,
                   'bridge_port': port, 'controller_instance': None, 'transport': 'files',
                   'rpc_directory': str(rpc_root.resolve()), 'rpc_prefix': rpc_prefix}
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = rpc_root / (rpc_prefix + 'state.json')
            if state.is_file():
                try:
                    observed = decode_json(state.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    observed = {}
                if observed.get('owner_marker') == marker and time.time() - observed.get('ts', 0) <= 3:
                    session['controller_instance'] = observed['instance']
                    break
            if process_stamp(session['pid']) is None:
                break
            time.sleep(.1)
        if session['controller_instance'] is None:
            exited = process_stamp(session['pid']) is None
            stop_worker(session)
            raise ValueError('Owned controller handshake was not confirmed; worker ' +
                             ('exited during startup.' if exited else 'was closed after the controller timeout.'))
    path = output / 'session.json'
    path.write_text(canonical_json(session), encoding='utf-8')
    return {**session, 'session': str(path.resolve())}


def save(session, output):
    from .flp import Project
    from .live import Bridge
    if process_stamp(session['pid']) != session['process_created']:
        raise ValueError('Owned session process has exited or changed')
    project = Path(session['project'])
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Choose a new output file with an existing parent')
    before = project.stat().st_mtime_ns
    client = Bridge(port=session['bridge_port'], session=session)
    client.call('cli_project_save')
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            if project.stat().st_mtime_ns != before:
                doc = Project.read(project)
                changed = client.call('cli_api_call', {'module': 'general', 'function': 'getChangedFlag'})['value']
                if not changed:
                    break
        except (FileNotFoundError, ValueError):
            # FL replaces its project file during save; the old path can be
            # absent briefly before the completed replacement is installed.
            pass
        time.sleep(.05)
    else:
        raise ValueError('FL save was not confirmed; no output copy was published')
    if session.get('owner_field') == 'title':
        from .fields import metadata, set_metadata
        if metadata(doc)['title'] != session['owner_marker']:
            raise ValueError('The saved project no longer belongs to the session')
        if session['original_title'] is None:
            doc.events[:] = [e for e in doc.events if e.id != 194]
        else:
            set_metadata(doc, {'title': session['original_title']})
    else:
        if not doc.channels() or doc.channels()[0]['name'] != session['owner_marker']:
            raise ValueError('The saved project no longer belongs to the session')
        doc.set_channel(0, {'name': session['first_channel_name']})
    doc.save(output)
    return {'output': str(output.resolve()), 'saved_by_fl': True, 'owned_marker_removed': True,
            'channel_count': len(doc.channels())}


def parameter_checks(request):
    import math
    if not isinstance(request, list) or not 1 <= len(request) <= 16:
        raise ValueError('Verification request requires an array of 1..16 explicit plugin targets')
    for group in request:
        if not isinstance(group, dict): raise ValueError('Plugin target must be an object')
        target = set(group) - {'params'}
        if target not in ({'channel'}, {'track', 'slot'}):
            raise ValueError('Choose channel or track+slot and a params array')
        if any(type(group[k]) is not int or group[k] < 0 for k in target):
            raise ValueError('Target indices must be nonnegative integers')
        values = group.get('params')
        if not isinstance(values, list) or not 1 <= len(values) <= 128:
            raise ValueError('Each target requires 1..128 parameter checks')
        for check in values:
            if (not isinstance(check, dict) or set(check) - {'param', 'expect'} or
                    type(check.get('param')) is not int or check['param'] < 0):
                raise ValueError('Each check requires param index and optional normalized expect')
            if 'expect' in check and (type(check['expect']) not in (int, float) or
                    not math.isfinite(check['expect']) or not 0 <= check['expect'] <= 1):
                raise ValueError('Expected values must be finite normalized 0..1')
    return request


def verify_params(session, request, output, install):
    from .live import Bridge
    from .json_output import canonical_json
    request = parameter_checks(request)
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Choose a new verification directory with an existing parent')
    if process_stamp(session['pid']) != session['process_created']:
        raise ValueError('Owned session process has exited or changed')
    client = Bridge(port=session['bridge_port'], session=session)
    state = client.call('get_play_state')
    session_info = client.call('cli_session_info')
    if state['playing'] or state['recording'] or session_info.get('active_plugin_jobs') or session_info.get('active_recording_jobs'):
        raise ValueError('Stop transport/recording and finish parameter transactions before a checkpoint')
    def observe(bridge):
        observations = []
        for group in request:
            target = {k: v for k, v in group.items() if k != 'params'}
            identity = bridge.call('cli_plugin_info', target)
            values = bridge.call('cli_plugin_read', {**target, 'params': [p['param'] for p in group['params']]})
            observations.append({'target': target, 'identity': identity, 'params': values['params']})
        return observations
    before = observe(client)
    output.mkdir()
    checkpoint = output / 'checkpoint.flp'
    saved = save(session, checkpoint)
    stable = before == observe(client)
    worker = None
    data = {'checkpoint': saved, 'source_stable_during_save': stable, 'host_before': before,
            'original_worker_restarted': False, 'display_equality_is_semantic_proof': False}
    try:
        worker = start(checkpoint, output / 'worker', install, session['bridge_port'], Path(session['rpc_directory']))
        reopened = observe(Bridge(port=session['bridge_port'], session=worker))
        data['reopened'] = reopened
        comparisons, bindings, expected, mismatches = [], True, 0, 0
        for spec, left, right in zip(request, before, reopened):
            same_plugin = all(left['identity'][key] == right['identity'][key] for key in ('plugin', 'total'))
            for check, a, b in zip(spec['params'], left['params'], right['params']):
                bound = same_plugin and a['i'] == b['i'] and a['name'] == b['name']
                bindings = bindings and bound
                row = {'target': left['target'], 'param': a['i'], 'name': a['name'], 'binding_verified': bound,
                       'host_before': a, 'reopened': b, 'numeric_equal': abs(a['v'] - b['v']) <= .0001,
                       'display_equal': a['s'] == b['s']}
                if 'expect' in check:
                    expected += 1
                    matched = bound and abs(b['v'] - check['expect']) <= .0001
                    row.update(expect=check['expect'], matches_expected=matched)
                    mismatches += not matched
                comparisons.append(row)
        data.update(comparisons=comparisons, bindings_verified=bindings, expectation_count=expected)
        if not bindings: status, reason = 'unknown', 'parameter_binding_changed'
        elif not stable: status, reason = 'unknown', 'source_changed_during_checkpoint'
        elif mismatches: status, reason = 'failed', 'persisted_value_mismatch'
        else: status, reason = 'verified', None
        scopes = []
        if bindings and stable:
            scopes.append('reopened_parameter_observation')
            if expected and not mismatches: scopes.append('reopened_parameter_expectations')
        data.update(status=status, reason_code=reason, verified_scopes=scopes)
    except (OSError, RuntimeError, ValueError) as error:
        data.update(status='unknown', reason_code='parameter_observation_unavailable', message=str(error), verified_scopes=[])
    finally:
        if worker is not None: data['verification_worker_stop'] = stop_worker(worker)
    (output / 'observations.json').write_text(canonical_json(data), encoding='utf-8')
    return data


def register(app, emit, json_option):
    import click
    from .contracts import Result
    from .json_output import decode_json
    from .live import Bridge
    @app.group('session')
    @json_option
    def group():
        """Run an addressed private FL worker, preserving the user's editor."""
    @group.command('start')
    @click.option('--project', 'source', required=True, type=click.Path(path_type=Path))
    @click.option('--output-dir', required=True, type=click.Path(path_type=Path))
    @click.option('--fl-install', default=Path('C:/Program Files/Image-Line/FL Studio 2026'), type=click.Path(path_type=Path))
    @click.option('--bridge-port', default=9787, type=click.IntRange(1, 65535))
    @click.option('--controller-dir', type=click.Path(path_type=Path))
    @click.option('--desktop', 'desktop_mode', type=click.Choice(['private', 'interactive']), default='private')
    @click.option('--dry-run', is_flag=True)
    @json_option
    def begin(source, output_dir, fl_install, bridge_port, controller_dir, desktop_mode, dry_run):
        if dry_run:
            emit(Result(command='session start', status='planned', data={'source': str(source), 'file_effects': [], 'process_started': False}))
            return
        data = start(source, output_dir, fl_install, bridge_port, controller_dir, desktop_mode)
        emit(Result(command='session start', status='verified', verified_scopes=['owned_process', 'addressed_controller'], data=data))
    @group.command('status')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @json_option
    def status(session):
        data = decode_json(session.read_text(encoding='utf-8-sig'))
        if process_stamp(data['pid']) != data['process_created']:
            raise ValueError('Owned session process has exited or changed')
        observed = Bridge(port=data['bridge_port'], session=data).call('cli_session_info')
        emit(Result(command='session status', status='verified', verified_scopes=['owned_process', 'addressed_controller'], data=observed))

    @group.command('windows')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @click.option('--children', is_flag=True, help='Include visible native child controls.')
    @json_option
    def windows(session, children):
        """List windows of this owned process, including its modal dialogs."""
        from .owned_ui import observe
        data = observe(decode_json(session.read_text(encoding='utf-8-sig')), children=children)
        emit(Result(command='session windows', status='verified', verified_scopes=['owned_window_identity'], data=data))

    @group.command('screenshot')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @click.option('--window', type=click.IntRange(1), help='Owned HWND returned by session windows; defaults to the unique FL main window.')
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--receipt', type=click.Path(path_type=Path), help='Save observation metadata for a later addressed input.')
    @json_option
    def screenshot(session, window, output, receipt):
        """Read an owned window into a new PNG/BMP; never activates the window."""
        from .owned_ui import observe
        from .json_output import canonical_json
        if receipt and (receipt.exists() or not receipt.parent.is_dir()):
            raise ValueError('Choose a new receipt path with an existing parent')
        data = observe(decode_json(session.read_text(encoding='utf-8-sig')), output, window)
        if receipt: receipt.write_text(canonical_json(data), encoding='utf-8')
        emit(Result(command='session screenshot', status='artifact_ready', verified_scopes=['owned_window_identity'], data=data))

    @group.command('input')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @click.option('--observation', required=True, type=click.Path(path_type=Path))
    @click.option('--key', type=click.Choice(['enter', 'escape', 'up', 'down', 'left', 'right', 'home', 'end', 'tab', 'space', 'backspace', 'delete', 'f7']))
    @click.option('--move', type=int, nargs=2, help='Window pixel X Y from the observed screenshot.')
    @click.option('--click', 'pointer_click', type=int, nargs=2)
    @click.option('--drag', type=int, nargs=4, help='Window pixel X1 Y1 X2 Y2.')
    @click.option('--dry-run', is_flag=True)
    @json_option
    def input_key(session, observation, key, move, pointer_click, drag, dry_run):
        """Submit addressed input to a captured private-owned window, then verify its effect."""
        from .owned_ui import submit_key, submit_pointer
        if sum(bool(v) for v in (key, move, pointer_click, drag)) != 1: raise ValueError('Choose exactly one key, move, click or drag')
        pointer = {'move': move} if move else {'click': pointer_click} if pointer_click else {'drag': [drag[:2], drag[2:]]} if drag else None
        owned = decode_json(session.read_text(encoding='utf-8-sig'))
        frame = decode_json(observation.read_text(encoding='utf-8-sig'))
        if 'data' in frame: frame = frame['data']
        if dry_run:
            emit(Result(command='session input', status='planned', data={'key': key, 'pointer': pointer, 'window': frame['window'],
                'submitted': False, 'file_effects': [], 'bridge_contacted': False})); return
        data = submit_key(owned, frame, key) if key else submit_pointer(owned, frame, pointer)
        emit(Result(command='session input', status='unknown', reason_code='input_submitted_effect_unverified', data=data))
    @group.command('stop')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @json_option
    def stop(session):
        data = decode_json(session.read_text(encoding='utf-8-sig'))
        emit(Result(command='session stop', status='verified', data=stop_worker(data)))

    @group.command('save')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def saved(session, output, dry_run):
        data = decode_json(session.read_text(encoding='utf-8-sig'))
        if dry_run:
            emit(Result(command='session save', status='planned', data={'output': str(output),
                        'bridge_contacted': False, 'file_effects': []}))
            return
        emit(Result(command='session save', status='artifact_ready', verified_scopes=['fl_authored_save'], data=save(data, output)))

    @group.command('verify-params')
    @click.option('--session', required=True, type=click.Path(path_type=Path))
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--output-dir', required=True, type=click.Path(path_type=Path))
    @click.option('--fl-install', default=Path('C:/Program Files/Image-Line/FL Studio 2026'), type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def verify(session, request, output_dir, fl_install, dry_run):
        """Save and reopen a private checkpoint; observe or assert plugin values."""
        checks = parameter_checks(decode_json(request.read_text(encoding='utf-8-sig')))
        if dry_run:
            emit(Result(command='session verify-params', status='planned', data={'checks': checks,
                'output': str(output_dir), 'bridge_contacted': False, 'file_effects': []})); return
        data = verify_params(decode_json(session.read_text(encoding='utf-8-sig')), checks, output_dir, fl_install)
        emit(Result(command='session verify-params', status=data['status'], reason_code=data['reason_code'],
                    verified_scopes=data['verified_scopes'], data=data))
        if data['status'] != 'verified': raise click.exceptions.Exit(5)
