"""Addressed file RPC, with compatibility for the existing local MIDI relay."""
from __future__ import annotations

import math
from pathlib import Path
import socket
import time
import uuid

import click

from .contracts import Result
from .json_output import canonical_json, decode_json

READ_COMMANDS = {
    'ping', 'get_tempo', 'get_project_state', 'get_play_state', 'get_song_position',
    'mixer_list_tracks', 'mixer_get_track', 'mixer_get_routing', 'mixer_get_routing_all',
    'channel_list', 'channel_get', 'channel_routing_summary', 'mixer_get_peaks',
    'plugin_list', 'plugin_get_params', 'plugin_get_param', 'pattern_list', 'pattern_get_length',
    'cli_capabilities', 'cli_channel_plugin_params', 'cli_channel_plugin_get_param',
    'cli_plugin_info', 'cli_plugin_params', 'cli_plugin_find', 'cli_plugin_get_param', 'cli_plugin_read',
    'cli_plugin_job', 'cli_api_catalog', 'cli_session_info',
}


class Bridge:
    def __init__(self, host='127.0.0.1', port=9787, session=None, editor_pid=None, controller_dir=None):
        self.host, self.port = host, port
        self.session = session
        self.editor_pid, self.controller_dir, self._resolved = editor_pid, controller_dir, session is not None

    @property
    def backend(self):
        if not self._resolved: return 'unresolved'
        return 'addressed_file_rpc' if self.session and self.session.get('transport') == 'files' else 'local_midi_bridge'

    def resolve(self):
        if self._resolved: return
        hardware = Path.home() / 'Documents/Image-Line/FL Studio/Settings/Hardware'
        roots = [self.controller_dir] if self.controller_dir else [hardware / 'FLStudioCLI', hardware / 'FLStudioMCP']
        candidates = []
        for root in roots:
            for path in Path(root).glob('editor-*-state.json'):
                try:
                    state = decode_json(path.read_text(encoding='utf-8'))
                    if (state.get('owner_marker') is None and time.time() - state['ts'] < 3 and
                            (self.editor_pid is None or state.get('pid') == self.editor_pid)):
                        candidates.append((path, state))
                except (OSError, ValueError, KeyError):
                    continue
        if len(candidates) > 1:
            raise RuntimeError('Multiple controller endpoints are active; choose one --editor-pid and controller directory')
        if candidates:
            path, state = candidates[0]
            self.session = {'transport': 'files', 'rpc_directory': str(path.parent),
                            'rpc_prefix': path.name[:-len('state.json')], 'controller_instance': state['instance'],
                            'owner_marker': None, 'pid': state['pid']}
        elif self.editor_pid is not None:
            raise RuntimeError('No fresh standalone controller endpoint for this editor PID; reload its controller')
        self._resolved = True

    def addressed(self):
        self.resolve()
        if self.session:
            return self
        from .midi_bridge import rpc
        candidates = [item for item in rpc(self.port, {'op': 'health'}).get('sessions', [])
                      if item.get('owner_marker') is None and item['heartbeat_age'] <= 3]
        if len(candidates) != 1:
            raise RuntimeError('Reload the CLI controller extension in one editor, or choose --session')
        self.session = {'controller_instance': candidates[0]['instance'], 'owner_marker': None}
        return self

    def call(self, command, params=None):
        self.resolve()
        if self.session and self.session.get('transport') == 'files':
            return self.file_call(command, params)
        request = {'op': 'call', 'cmd': command, 'params': params, 'timeout': 5.0}
        if self.session:
            request.update(instance=self.session['controller_instance'], owner_marker=self.session['owner_marker'])
        with socket.create_connection((self.host, self.port), timeout=6) as connection:
            connection.sendall((canonical_json(request) + '\n').encode('utf-8'))
            with connection.makefile('rb') as reader:
                reply = decode_json(reader.readline().decode('utf-8'))
        if not reply.get('ok'):
            raise RuntimeError(reply.get('error', 'Local MIDI bridge rejected the request'))
        return reply['data']

    def file_call(self, command, params):
        import msvcrt
        folder = Path(self.session['rpc_directory'])
        with (folder / (self.session['rpc_prefix'] + 'lock')).open('a+b') as lock:
            if lock.tell() == 0:
                lock.write(b'0'); lock.flush()
            deadline = time.monotonic() + 6
            while True:
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Another client is still using this owned session')
                    time.sleep(.01)
            try:
                return self._file_call_locked(command, params)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def _file_call_locked(self, command, params):
        folder = Path(self.session['rpc_directory'])
        for attempt in range(4):
            try:
                state = decode_json((folder / (self.session['rpc_prefix'] + 'state.json')).read_text(encoding='utf-8'))
                break
            except ValueError:
                if attempt == 3:
                    raise RuntimeError('Owned controller state could not be read')
                time.sleep(.01)
        if (state.get('instance') != self.session['controller_instance'] or
                state.get('owner_marker') != self.session['owner_marker'] or time.time() - state['ts'] > 3):
            raise RuntimeError('Owned controller has changed or stopped responding')
        identifier = uuid.uuid4().hex
        request = folder / (self.session['rpc_prefix'] + 'request.json')
        response = folder / (self.session['rpc_prefix'] + 'response.json')
        temporary = request.with_suffix('.tmp')
        payload = {'id': identifier, 'cmd': command, 'params': params or {}, 'instance': self.session['controller_instance'],
                   'owner_marker': self.session['owner_marker'], 'expires_at': time.time() + 5}
        temporary.write_text(canonical_json(payload), encoding='utf-8')
        # FL briefly opens the previous request on every OnIdle. Windows can
        # deny replacement while that read handle exists; no new request has
        # been submitted yet, so retry this same atomic rename, not the write.
        rename_deadline = time.monotonic() + .5
        while True:
            try:
                temporary.replace(request)
                break
            except PermissionError:
                if time.monotonic() >= rename_deadline: raise
                time.sleep(.005)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if response.is_file():
                try:
                    reply = decode_json(response.read_text(encoding='utf-8'))
                except ValueError:
                    time.sleep(.01)
                    continue
                if reply.get('instance') != self.session['controller_instance'] or reply.get('id') != identifier:
                    time.sleep(.01)
                    continue
                if not reply.get('ok'):
                    raise RuntimeError(reply.get('error', 'Owned FL rejected the request'))
                return reply['data']
            time.sleep(.01)
        request.unlink(missing_ok=True)
        raise RuntimeError(f'Owned FL did not complete {command!r}; read back its state before retrying writes')

    def parameters(self, track=None, slot=None, channel=None, search=''):
        params, start = [], 0
        while True:
            page = (self.call('cli_channel_plugin_params', {'channel': channel, 'start': start, 'search': search})
                    if channel is not None else self.call('plugin_get_params', {'track': track, 'slot': slot, 'start': start}))
            params.extend(page['params'])
            following = page.get('next_start')
            if following is None:
                return [p for p in params if search.casefold() in p['name'].casefold()]
            if following <= start:
                raise RuntimeError('Plugin parameter page did not advance')
            start = following

    def plugin_job(self, job_id):
        result, changes, start = None, [], 0
        while True:
            page = self.call('cli_plugin_job', {'id': job_id, 'start': start})
            result = page if result is None else result
            changes.extend(page['changes'])
            following = page['next_start']
            if following is None:
                result.update(changes=changes, next_start=None)
                return result
            if following <= start:
                raise RuntimeError('Transaction page did not advance')
            start = following

    def wait_plugin_job(self, job_id, count):
        deadline = time.monotonic() + 2 + count * 1.7
        while True:
            page = self.call('cli_plugin_job', {'id': job_id})
            if page['state'] not in ('queued', 'checking', 'rollback'):
                return self.plugin_job(job_id)
            if time.monotonic() >= deadline:
                return {'id': job_id, 'state': 'unknown', 'error': 'Client wait expired; query or cancel this job'}
            time.sleep(.03)


def register(app, emit, json_option):
    @app.group('live')
    @click.option('--bridge-host', default='127.0.0.1')
    @click.option('--bridge-port', default=9787, type=click.IntRange(1, 65535))
    @click.option('--session', type=click.Path(path_type=Path), help='Bind to an owned session JSON, not the user editor.')
    @click.option('--editor-pid', type=click.IntRange(1))
    @click.option('--controller-dir', type=click.Path(path_type=Path))
    @click.pass_context
    @json_option
    def live(ctx, bridge_host, bridge_port, session, editor_pid, controller_dir):
        """Control a standalone FL controller or an explicitly owned session."""
        if session and editor_pid: raise ValueError('Choose --session or --editor-pid')
        ctx.obj = Bridge(bridge_host, bridge_port, decode_json(session.read_text(encoding='utf-8-sig')) if session else None,
                         editor_pid, controller_dir)

    def execute(command, function):
        try:
            return function()
        except click.exceptions.Exit:
            raise
        except (OSError, RuntimeError) as error:
            emit(Result(command=command, status='failed', reason_code='live_bridge_error',
                        data={'message': str(error)}))
            raise click.exceptions.Exit(5)

    def write(command, bridge, setter, params, getter, read_params, field, value, dry_run):
        if dry_run:
            emit(Result(command=command, status='planned', data={'command': setter, 'params': params,
                        'live_applied': False, 'applied_count': None, 'file_effects': [], 'bridge_contacted': False}))
            return
        def apply():
            before = bridge.call(getter, read_params)
            bridge.call(setter, params)
            deadline = time.monotonic() + 1.5
            while True:
                after = bridge.call(getter, read_params)
                actual = after.get(field)
                confirmed = isinstance(actual, (int, float)) and math.isclose(actual, value, abs_tol=.0001)
                if confirmed or time.monotonic() >= deadline:
                    break
                time.sleep(.04)
            emit(Result(command=command, status='verified' if confirmed else 'unknown',
                        reason_code=None if confirmed else 'live_value_not_confirmed',
                        verified_scopes=['live_host_parameter_value' if field == 'v' else 'live_value'] if confirmed else [],
                        data={'backend': bridge.backend, 'before': before, 'after': after,
                              'submitted': True, 'live_applied': True if confirmed else None,
                              'verification_scope': 'host_readback', 'persistence_verified': False,
                              'source_file_saved': False}))
            if not confirmed:
                raise click.exceptions.Exit(5)
        execute(command, apply)

    @live.command('status')
    @click.pass_obj
    @json_option
    def status(bridge):
        def read():
            project = bridge.call('get_project_state')
            emit(Result(command='live status', status='verified', verified_scopes=['live_project_state'],
                        data={'backend': bridge.backend, 'project': project}))
        execute('live status', read)

    @live.command('set-tempo')
    @click.option('--bpm', required=True, type=click.FloatRange(10, 522))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def set_tempo(bridge, bpm, dry_run):
        write('live set-tempo', bridge, 'set_tempo', {'bpm': bpm}, 'get_tempo', None, 'bpm', bpm, dry_run)

    @live.command('mixer-track')
    @click.option('--track', required=True, type=click.IntRange(0, 501))
    @click.pass_obj
    @json_option
    def mixer_track(bridge, track):
        execute('live mixer-track', lambda: emit(Result(command='live mixer-track', status='verified',
                verified_scopes=['live_mixer_track'], data=bridge.call('mixer_get_track', {'index': track}))))

    @live.command('set-mixer-pan')
    @click.option('--track', required=True, type=click.IntRange(0, 501))
    @click.option('--value', required=True, type=click.FloatRange(-1, 1))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def set_pan(bridge, track, value, dry_run):
        write('live set-mixer-pan', bridge, 'mixer_set_pan', {'track': track, 'value': value},
              'mixer_get_track', {'index': track}, 'pan', value, dry_run)

    @live.command('plugin-params')
    @click.option('--track', type=click.IntRange(0, 501))
    @click.option('--slot', type=click.IntRange(0, 9))
    @click.option('--channel', type=click.IntRange(0, 4095), help='Global generator channel; requires CLI controller extension.')
    @click.option('--search', default='')
    @click.pass_obj
    @json_option
    def plugin_params(bridge, track, slot, channel, search):
        target = plugin_target(track, slot, channel)
        execute('live plugin-params', lambda: emit(Result(command='live plugin-params', status='verified',
                verified_scopes=['live_plugin_params'], data={**target,
                'params': bridge.parameters(track, slot, channel, search)})))

    def plugin_target(track, slot, channel):
        if channel is not None and track is None and slot is None:
            return {'channel': channel, 'index_scope': 'global'}
        if channel is None and track is not None and slot is not None:
            return {'track': track, 'slot': slot}
        raise ValueError('Choose exactly --channel or --track with --slot')

    @live.command('set-plugin-param')
    @click.option('--track', type=click.IntRange(0, 501))
    @click.option('--slot', type=click.IntRange(0, 9))
    @click.option('--channel', type=click.IntRange(0, 4095))
    @click.option('--param', required=True, help='Exact live name or numeric index; ambiguous names are rejected.')
    @click.option('--value', required=True, type=click.FloatRange(0, 1))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def set_param(bridge, track, slot, channel, param, value, dry_run):
        location = plugin_target(track, slot, channel)
        setter = 'cli_channel_plugin_set_param' if channel is not None else 'plugin_set_param'
        getter = 'cli_channel_plugin_get_param' if channel is not None else 'plugin_get_param'
        location.pop('index_scope', None)
        # A preview must not even resolve names over the bridge.
        if dry_run:
            write('live set-plugin-param', bridge, setter,
                  {**location, 'param': param, 'value': value}, None, None, 'v', value, True)
            return
        def apply():
            if param.isdecimal():
                index = int(param)
            else:
                matches = [p for p in bridge.parameters(track, slot, channel, param) if p['name'].casefold() == param.casefold()]
                if len(matches) != 1:
                    raise ValueError('Parameter name must identify exactly one live parameter')
                index = matches[0]['i']
            target = {**location, 'param': index}
            write('live set-plugin-param', bridge, setter, {**target, 'value': value}, getter, target, 'v', value, False)
        execute('live set-plugin-param', apply)

    @live.command('plugin-find')
    @click.option('--track', type=click.IntRange(0, 501))
    @click.option('--slot', type=click.IntRange(0, 9))
    @click.option('--channel', type=click.IntRange(0, 4095))
    @click.option('--search', required=True)
    @click.pass_obj
    @json_option
    def plugin_find(bridge, track, slot, channel, search):
        location = plugin_target(track, slot, channel)
        def find():
            client, found, start = bridge.addressed(), [], 0
            while True:
                page = client.call('cli_plugin_find', {**location, 'search': search, 'start': start})
                found.extend(page['matches'])
                following = page['next_start']
                if following is None:
                    break
                if following <= start:
                    raise RuntimeError('Parameter search page did not advance')
                start = following
            emit(Result(command='live plugin-find', status='verified', verified_scopes=['live_parameter_names'],
                        data={**location, 'matches': found}))
        execute('live plugin-find', find)

    @live.command('plugin-apply')
    @click.option('--track', type=click.IntRange(0, 501))
    @click.option('--slot', type=click.IntRange(0, 9))
    @click.option('--channel', type=click.IntRange(0, 4095))
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def plugin_apply(bridge, track, slot, channel, request, dry_run):
        location = plugin_target(track, slot, channel)
        changes = decode_json(request.read_text(encoding='utf-8-sig'))
        if not isinstance(changes, list) or not 1 <= len(changes) <= 32:
            raise ValueError('Request must be an array of 1..32 parameter changes')
        if dry_run:
            emit(Result(command='live plugin-apply', status='planned', data={**location, 'changes': changes,
                        'bridge_contacted': False, 'live_applied': False, 'file_effects': []}))
            return
        def apply():
            client = bridge.addressed()
            queued = client.call('cli_plugin_apply', {**location, 'changes': changes})
            result = queued if queued['state'] == 'verified' and 'changes' in queued else client.wait_plugin_job(queued['id'], len(changes))
            confirmed = result['state'] == 'verified'
            emit(Result(command='live plugin-apply', status='verified' if confirmed else 'unknown',
                        reason_code=None if confirmed else 'parameter_transaction_' + result['state'],
                        verified_scopes=['live_host_parameter_values'] if confirmed else [], data={**location, **result,
                        'source_file_saved': False}))
            if not confirmed:
                raise click.exceptions.Exit(5)
        execute('live plugin-apply', apply)

    @live.command('plugin-job')
    @click.option('--id', 'job_id', required=True)
    @click.option('--cancel', is_flag=True)
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def plugin_job(bridge, job_id, cancel, dry_run):
        if dry_run:
            emit(Result(command='live plugin-job', status='planned', data={'id': job_id, 'cancel': cancel,
                        'bridge_contacted': False, 'file_effects': []}))
            return
        def read_job():
            client = bridge.addressed()
            if cancel:
                client.call('cli_plugin_cancel', {'id': job_id})
            result = client.plugin_job(job_id)
            emit(Result(command='live plugin-job', status='verified', verified_scopes=['transaction_status'], data=result))
        execute('live plugin-job', read_job)

    @live.command('api-catalog')
    @click.option('--module')
    @click.option('--constants', is_flag=True)
    @click.option('--search', default='')
    @click.pass_obj
    @json_option
    def api_catalog(bridge, module, constants, search):
        def catalog():
            client, result, names, start = bridge.addressed(), None, [], 0
            while True:
                page = client.call('cli_api_catalog', {'module': module, 'kind': 'constants' if constants else 'functions',
                                                       'search': search, 'start': start})
                if module is None:
                    result = page
                    break
                result = page if result is None else result
                names.extend(page['functions'])
                following = page['next_start']
                if following is None:
                    result.update(functions=names, next_start=None)
                    break
                if following <= start:
                    raise RuntimeError('API catalog page did not advance')
                start = following
            emit(Result(command='live api-catalog', status='verified', verified_scopes=['available_fl_api'], data=result))
        execute('live api-catalog', catalog)

    @live.command('api')
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def api(bridge, request, dry_run):
        """Call a public FL function; writes accept an independent readback."""
        spec = decode_json(request.read_text(encoding='utf-8-sig'))
        allowed = {'module', 'function', 'args', 'kwargs', 'readback'}
        if not isinstance(spec, dict) or set(spec) - allowed or not {'module', 'function'} <= set(spec):
            raise ValueError('API request requires module, function, optional args, kwargs and readback')
        check = spec.get('readback')
        if check is not None and (not isinstance(check, dict) or 'expect' not in check or
                                  not {'module', 'function'} <= set(check)):
            raise ValueError('API readback requires module, function, expect and optional args/kwargs')
        if dry_run:
            emit(Result(command='live api', status='planned', data={'request': spec, 'bridge_contacted': False, 'file_effects': []}))
            return
        def call():
            client = bridge.addressed()
            response = client.call('cli_api_call', {k: v for k, v in spec.items() if k != 'readback'})
            observed, confirmed = None, False
            if check is not None:
                deadline = time.monotonic() + 1.5
                while True:
                    observed = client.call('cli_api_call', {k: v for k, v in check.items() if k != 'expect'})
                    confirmed = observed['value'] == check['expect']
                    if confirmed or time.monotonic() >= deadline:
                        break
                    time.sleep(.03)
            is_read = spec['function'].startswith(('get', 'is', 'find'))
            ok = confirmed or (check is None and is_read)
            emit(Result(command='live api', status='verified' if ok else 'unknown',
                        reason_code=None if ok else 'api_postcondition_not_confirmed',
                        verified_scopes=['api_postcondition' if confirmed else 'api_return'] if ok else [],
                        data={'return': response, 'readback': observed, 'source_file_saved': False}))
            if not ok:
                raise click.exceptions.Exit(5)
        execute('live api', call)

    @live.command('api-batch')
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def api_batch(bridge, request, dry_run):
        calls = decode_json(request.read_text(encoding='utf-8-sig'))
        if not isinstance(calls, list) or not 1 <= len(calls) <= 128:
            raise ValueError('Request requires an array of 1..128 public API calls')
        if dry_run:
            emit(Result(command='live api-batch', status='planned', data={'calls': calls, 'bridge_contacted': False, 'file_effects': []})); return
        def run():
            result = bridge.addressed().call('cli_api_batch', {'calls': calls})
            # Raw batches expose API returns, not fabricated semantic success.
            reads = all(isinstance(c.get('function'), str) and c['function'].startswith(('get', 'is', 'find')) for c in calls)
            ok = result['complete'] and reads
            emit(Result(command='live api-batch', status='verified' if ok else 'unknown',
                        reason_code=None if ok else 'api_postconditions_not_verified',
                        verified_scopes=['api_returns'] if ok else [], data=result))
            if not ok: raise click.exceptions.Exit(5)
        execute('live api-batch', run)

    @live.command('query')
    @click.option('--command', required=True, type=click.Choice(sorted(READ_COMMANDS)))
    @click.option('--params-file', type=click.Path(path_type=Path))
    @click.pass_obj
    @json_option
    def query(bridge, command, params_file):
        """Read a controller primitive; parameter names are in docs/live-commands.md."""
        params = {} if params_file is None else decode_json(params_file.read_text(encoding='utf-8-sig'))
        if not isinstance(params, dict):
            raise ValueError('Query parameters must be a JSON object')
        execute('live query', lambda: emit(Result(command='live query', status='verified',
                verified_scopes=['live_readback'], data={'command': command, 'result': bridge.call(command, params)})))

    @live.command('apply')
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def apply_primitive(bridge, request, dry_run):
        """Write a controller primitive with an explicit readback condition."""
        spec = decode_json(request.read_text(encoding='utf-8-sig'))
        if not isinstance(spec, dict) or set(spec) != {'command', 'params', 'readback'}:
            raise ValueError('Request requires command, params and readback')
        check = spec['readback']
        if (not isinstance(spec['command'], str) or not spec['command'] or not isinstance(spec['params'], dict)
                or not isinstance(check, dict) or set(check) != {'command', 'params', 'expect'}
                or check['command'] not in READ_COMMANDS or not isinstance(check['params'], dict)
                or not isinstance(check['expect'], dict) or not check['expect']):
            raise ValueError('Readback requires a known read command, object params and nonempty expect object')
        if dry_run:
            emit(Result(command='live apply', status='planned', data={'request': spec, 'bridge_contacted': False,
                        'live_applied': False, 'file_effects': [], 'applied_count': None}))
            return

        def apply():
            before = bridge.call(check['command'], check['params'])
            response = bridge.call(spec['command'], spec['params'])
            deadline = time.monotonic() + 1.5

            def equal(expected, actual):
                if isinstance(expected, bool):
                    return expected is actual
                if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                    return math.isclose(expected, actual, rel_tol=0, abs_tol=.0001)
                return expected == actual

            while True:
                after = bridge.call(check['command'], check['params'])
                confirmed = isinstance(after, dict) and all(k in after and equal(v, after[k]) for k, v in check['expect'].items())
                if confirmed or time.monotonic() >= deadline:
                    break
                time.sleep(.04)
            emit(Result(command='live apply', status='verified' if confirmed else 'unknown',
                        reason_code=None if confirmed else 'live_value_not_confirmed',
                        verified_scopes=['live_readback'] if confirmed else [],
                        data={'backend': bridge.backend, 'request': spec, 'before': before, 'after': after,
                              'response': response, 'submitted': True, 'live_applied': True if confirmed else None,
                              'source_file_saved': False}))
            if not confirmed:
                raise click.exceptions.Exit(5)
        execute('live apply', apply)
