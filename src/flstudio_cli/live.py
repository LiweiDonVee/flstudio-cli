"""Optional compatibility client for an existing local MIDI bridge.

The file backend remains independent. This adapter uses the deployed bridge's
newline JSON transport directly, without importing or launching an MCP server.
"""
from __future__ import annotations

import math
import socket
import time

import click

from .contracts import Result
from .json_output import canonical_json, decode_json


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

    def parameters(self, track, slot):
        params, start = [], 0
        while True:
            page = self.call('plugin_get_params', {'track': track, 'slot': slot, 'start': start})
            params.extend(page['params'])
            following = page.get('next_start')
            if following is None:
                return params
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
                        data={'message': str(error), 'backend': 'existing_midi_bridge'}))
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
                        data={'backend': 'existing_midi_bridge', 'before': before, 'after': after,
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
                verified_scopes=['live_project_state'], data={'backend': 'existing_midi_bridge',
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
    @click.option('--track', required=True, type=click.IntRange(0, 125))
    @click.option('--slot', required=True, type=click.IntRange(0, 9))
    @click.pass_obj
    @json_option
    def plugin_params(bridge, track, slot):
        execute('live plugin-params', lambda: emit(Result(command='live plugin-params', status='verified',
                verified_scopes=['live_plugin_params'], data={'track': track, 'slot': slot,
                'params': bridge.parameters(track, slot)})))

    @live.command('set-plugin-param')
    @click.option('--track', required=True, type=click.IntRange(0, 125))
    @click.option('--slot', required=True, type=click.IntRange(0, 9))
    @click.option('--param', required=True, help='Exact live name or numeric index; ambiguous names are rejected.')
    @click.option('--value', required=True, type=click.FloatRange(0, 1))
    @click.option('--dry-run', is_flag=True)
    @click.pass_obj
    @json_option
    def set_param(bridge, track, slot, param, value, dry_run):
        # A preview must not even resolve names over the bridge.
        if dry_run:
            write('live set-plugin-param', bridge, 'plugin_set_param',
                  {'track': track, 'slot': slot, 'param': param, 'value': value}, None, None, 'v', value, True)
            return
        def apply():
            if param.isdecimal():
                index = int(param)
            else:
                matches = [p for p in bridge.parameters(track, slot) if p['name'].casefold() == param.casefold()]
                if len(matches) != 1:
                    raise ValueError('Parameter name must identify exactly one live parameter')
                index = matches[0]['i']
            target = {'track': track, 'slot': slot, 'param': index}
            write('live set-plugin-param', bridge, 'plugin_set_param', {**target, 'value': value},
                  'plugin_get_param', target, 'v', value, False)
        execute('live set-plugin-param', apply)
