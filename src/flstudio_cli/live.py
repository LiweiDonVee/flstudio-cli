"""Optional compatibility client for an existing local MIDI bridge.

The file backend remains independent. This adapter uses the deployed bridge's
newline JSON transport directly, without importing or launching an MCP server.
"""
from __future__ import annotations

import math
from pathlib import Path
import socket
import time

import click

from .contracts import Result
from .json_output import canonical_json, decode_json

READ_COMMANDS = {
    'ping', 'get_tempo', 'get_project_state', 'get_play_state', 'get_song_position',
    'mixer_list_tracks', 'mixer_get_track', 'mixer_get_routing', 'mixer_get_routing_all',
    'channel_list', 'channel_get', 'channel_routing_summary', 'mixer_get_peaks',
    'plugin_list', 'plugin_get_params', 'plugin_get_param', 'pattern_list', 'pattern_get_length',
    'cli_capabilities', 'cli_channel_plugin_params', 'cli_channel_plugin_get_param',
}


class Bridge:
    def __init__(self, host='127.0.0.1', port=9787):
        self.host, self.port = host, port

    def call(self, command, params=None):
        request = {'op': 'call', 'cmd': command, 'params': params, 'timeout': 5.0}
        with socket.create_connection((self.host, self.port), timeout=6) as connection:
            connection.sendall((canonical_json(request) + '\n').encode('utf-8'))
            with connection.makefile('rb') as reader:
                reply = decode_json(reader.readline().decode('utf-8'))
        if not reply.get('ok'):
            raise RuntimeError(reply.get('error', 'Local MIDI bridge rejected the request'))
        return reply['data']

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


def register(app, emit, json_option):
    @app.group('live')
    @click.option('--bridge-host', default='127.0.0.1')
    @click.option('--bridge-port', default=9787, type=click.IntRange(1, 65535))
    @click.pass_context
    @json_option
    def live(ctx, bridge_host, bridge_port):
        """Control the open FL via an already configured local MIDI bridge."""
        ctx.obj = Bridge(bridge_host, bridge_port)

    def execute(command, function):
        try:
            return function()
        except click.exceptions.Exit:
            raise
        except (OSError, RuntimeError) as error:
            emit(Result(command=command, status='failed', reason_code='live_bridge_error',
                        data={'message': str(error), 'backend': 'local_midi_bridge'}))
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
                        verified_scopes=['live_value'] if confirmed else [],
                        data={'backend': 'local_midi_bridge', 'before': before, 'after': after,
                              'submitted': True, 'live_applied': True if confirmed else None,
                              'source_file_saved': False}))
            if not confirmed:
                raise click.exceptions.Exit(5)
        execute(command, apply)

    @live.command('status')
    @click.pass_obj
    @json_option
    def status(bridge):
        execute('live status', lambda: emit(Result(command='live status', status='verified',
                verified_scopes=['live_project_state'], data={'backend': 'local_midi_bridge',
                'project': bridge.call('get_project_state')})))

    @live.command('set-tempo')
    @click.option('--bpm', required=True, type=click.FloatRange(10, 522))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def set_tempo(bridge, bpm, dry_run):
        write('live set-tempo', bridge, 'set_tempo', {'bpm': bpm}, 'get_tempo', None, 'bpm', bpm, dry_run)

    @live.command('mixer-track')
    @click.option('--track', required=True, type=click.IntRange(0, 125))
    @click.pass_obj
    @json_option
    def mixer_track(bridge, track):
        execute('live mixer-track', lambda: emit(Result(command='live mixer-track', status='verified',
                verified_scopes=['live_mixer_track'], data=bridge.call('mixer_get_track', {'index': track}))))

    @live.command('set-mixer-pan')
    @click.option('--track', required=True, type=click.IntRange(0, 125))
    @click.option('--value', required=True, type=click.FloatRange(-1, 1))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def set_pan(bridge, track, value, dry_run):
        write('live set-mixer-pan', bridge, 'mixer_set_pan', {'track': track, 'value': value},
              'mixer_get_track', {'index': track}, 'pan', value, dry_run)

    @live.command('plugin-params')
    @click.option('--track', type=click.IntRange(0, 125))
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
    @click.option('--track', type=click.IntRange(0, 125))
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
                        data={'backend': 'local_midi_bridge', 'request': spec, 'before': before, 'after': after,
                              'response': response, 'submitted': True, 'live_applied': True if confirmed else None,
                              'source_file_saved': False}))
            if not confirmed:
                raise click.exceptions.Exit(5)
        execute('live apply', apply)
