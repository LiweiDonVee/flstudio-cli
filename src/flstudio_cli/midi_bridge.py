"""CLI-owned MIDI relay, compatible with the installed FL controller protocol."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time

import click

from . import __version__
from .contracts import Result
from .json_output import canonical_json, decode_json

BACKEND = 'flstudio_cli_midi'
PREFIX = b'\x7dMCP'
SESSION_PREFIX = b'\x7dFCL'


def rpc(port, request):
    with socket.create_connection(('127.0.0.1', port), timeout=3) as connection:
        connection.sendall((canonical_json(request) + '\n').encode('utf-8'))
        return decode_json(connection.makefile('rb').readline().decode('utf-8'))


def ensure_windows_midi():
    """Start the installed loopMIDI helper at login if it is not running."""
    if os.name != 'nt':
        return
    try:
        import mido
    except ImportError as error:
        raise RuntimeError('Install the CLI midi extra: uv tool install --editable ".[midi]" --python 3.12') from error

    def ports_ready():
        return (any('flstudiomcp tx' in name.casefold() for name in mido.get_input_names())
                and any('flstudiomcp rx' in name.casefold() for name in mido.get_output_names()))

    if ports_ready():
        return
    program = Path('C:/Program Files (x86)/Tobias Erichsen/loopMIDI/loopMIDI.exe')
    processes = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq loopMIDI.exe', '/FO', 'CSV', '/NH'],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if program.is_file() and b'loopmidi.exe' not in processes.stdout.lower():
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        subprocess.Popen([str(program)], startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if ports_ready():
                return
            time.sleep(.1)


class MidiRelay:
    def __init__(self, output_pattern, input_pattern):
        try:
            import mido
        except ImportError as error:
            raise RuntimeError('Install the CLI midi extra: uv tool install --editable ".[midi]" --python 3.12') from error
        self.mido = mido
        self.request_lock = threading.Lock()
        self.pending_lock = threading.Lock()
        self.pending = {}
        self.last_heartbeat = None
        self.controller = None
        self.controllers = {}
        self.heartbeat = threading.Event()

        def resolve(pattern, names):
            matches = [name for name in names if pattern.casefold() in name.casefold()]
            if len(matches) != 1:
                raise RuntimeError(f'MIDI port {pattern!r} must identify one port; available: {names}')
            return matches[0]

        self.port_to_fl = resolve(output_pattern, mido.get_output_names())
        self.port_from_fl = resolve(input_pattern, mido.get_input_names())
        self.output = mido.open_output(self.port_to_fl)
        try:
            self.input = mido.open_input(self.port_from_fl, callback=self.receive)
        except Exception:
            self.output.close()
            raise
        # FL can restore RX as a second output on the same numbered port.
        # Accept protocol replies from that loop too; request echoes (dir=1)
        # are ignored by receive, so this does not execute commands twice.
        self.return_input = None
        self.return_input_error = None
        alternate = [n for n in mido.get_input_names() if output_pattern.casefold() in n.casefold()]
        if len(alternate) == 1 and alternate[0] != self.port_from_fl:
            try:
                self.return_input = mido.open_input(alternate[0], callback=self.receive)
            except OSError as error:
                self.return_input_error = str(error)

    def close(self):
        if self.return_input is not None:
            self.return_input.close()
        self.input.close()
        self.output.close()

    def receive(self, message):
        if message.type != 'sysex':
            return
        packet = bytes(message.data)
        if len(packet) < 13 or packet[:4] not in (PREFIX, SESSION_PREFIX):
            return
        encoded = packet[13:]
        if packet[:4] == SESSION_PREFIX and packet[4] == 5:
            if len(packet) < 15:
                return
            identifier, part, count = packet[5:13].decode('ascii'), packet[13], packet[14]
            if not 0 <= part < count <= 127:
                return
            with self.pending_lock:
                slot = self.pending.get(identifier)
                if slot is None:
                    return
                pieces = slot.setdefault('pieces', {})
                pieces[part] = packet[15:]
                if len(pieces) != count:
                    return
                encoded = b''.join(pieces[i] for i in range(count))
        try:
            payload = json.loads(base64.b64decode(encoded, validate=True).decode('utf-8'))
        except (ValueError, UnicodeError):
            return
        if packet[4] == 3:
            if packet[:4] == SESSION_PREFIX:
                self.controllers[payload['instance']] = {**payload, 'received_at': time.monotonic()}
            else:
                self.last_heartbeat = time.monotonic()
                self.controller = payload
                self.heartbeat.set()
        elif packet[4] in (2, 5):
            identifier = packet[5:13].decode('ascii')
            with self.pending_lock:
                slot = self.pending.get(identifier)
                if slot is not None and (slot.get('instance') is None or payload.get('instance') == slot['instance']):
                    slot['reply'] = payload
                    slot['ready'].set()

    def health(self):
        age = None if self.last_heartbeat is None else max(0, time.monotonic() - self.last_heartbeat)
        return {'backend': BACKEND, 'version': __version__, 'pid': os.getpid(),
                'alive': age is not None and age <= 3, 'heartbeat_age': age,
                'port_to_fl': self.port_to_fl, 'port_from_fl': self.port_from_fl,
                'alternate_return_port': self.return_input.name if self.return_input else None,
                'alternate_return_error': self.return_input_error, 'controller': self.controller,
                'sessions': [{**value, 'heartbeat_age': max(0, time.monotonic() - value['received_at'])}
                             for value in self.controllers.values() if time.monotonic() - value['received_at'] < 30]}

    def call(self, command, params, timeout, instance=None, owner_marker=None):
        with self.request_lock:
            if self.last_heartbeat is None:
                self.heartbeat.wait(3)
            observed = self.controllers.get(instance) if instance else None
            alive = (observed is not None and time.monotonic() - observed['received_at'] <= 3) if instance else self.health()['alive']
            if not alive:
                return {'ok': False, 'error': 'FL controller heartbeat is missing or stale', 'code': 'fl_not_connected'}
            identifier = secrets.token_hex(4)
            request = {'v': 2, 'cmd': command, 'params': params or {}}
            if instance:
                request.update(instance=instance, owner_marker=owner_marker)
            encoded = base64.b64encode(canonical_json(request).encode('utf-8'))
            packet = (SESSION_PREFIX if instance else PREFIX) + b'\x01' + identifier.encode('ascii') + encoded
            if not instance and len(packet) > 1000:
                return {'ok': False, 'error': 'Request exceeds safe MIDI budget; use smaller batches or parameter indices'}
            if instance and len(encoded) > 720 * 127:
                return {'ok': False, 'error': 'Request exceeds 68 KiB; select a smaller operation'}
            slot = {'ready': threading.Event(), 'reply': None, 'instance': instance}
            with self.pending_lock:
                self.pending[identifier] = slot
            try:
                if instance and len(encoded) > 720:
                    count = (len(encoded) + 719) // 720
                    for index in range(count):
                        fragment = SESSION_PREFIX + b'\x04' + identifier.encode('ascii') + bytes([index, count]) + encoded[index * 720:(index + 1) * 720]
                        self.output.send(self.mido.Message('sysex', data=fragment))
                else:
                    self.output.send(self.mido.Message('sysex', data=packet))
                if not slot['ready'].wait(timeout):
                    return {'ok': False, 'error': f'FL did not answer {command!r} in {timeout}s', 'code': 'fl_timeout'}
                reply = slot['reply']
                if reply.get('v') != 2:
                    return {'ok': False, 'error': 'FL controller protocol must be version 2'}
                return reply
            finally:
                with self.pending_lock:
                    self.pending.pop(identifier, None)


def serve(port, midi_out, midi_in):
    relay = MidiRelay(midi_out, midi_in)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                request = decode_json(self.rfile.readline().decode('utf-8'))
                if request.get('op') == 'health':
                    result = relay.health()
                elif request.get('op') == 'call':
                    result = relay.call(request['cmd'], request.get('params'), min(120, max(.1, float(request.get('timeout', 5)))),
                                        request.get('instance'), request.get('owner_marker'))
                elif request.get('op') == 'shutdown':
                    result = {'ok': True, 'backend': BACKEND}
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    result = {'ok': False, 'error': 'Unknown CLI bridge operation'}
                self.wfile.write((canonical_json(result) + '\n').encode('utf-8'))
            except (ValueError, KeyError, OSError) as error:
                self.wfile.write((canonical_json({'ok': False, 'error': str(error)}) + '\n').encode('utf-8'))

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    try:
        with Server(('127.0.0.1', port), Handler) as server:
            server.serve_forever()
    finally:
        relay.close()


def register(app, emit, json_option):
    @app.group('bridge')
    @json_option
    def bridge_group():
        """Run the CLI's own MIDI relay without an MCP server or daemon."""

    @bridge_group.command('install-controller')
    @click.option('--controller-dir', type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def install_controller(controller_dir, dry_run):
        """Install the standalone controller; preserve an existing FL binding."""
        import shutil
        hardware = Path.home() / 'Documents/Image-Line/FL Studio/Settings/Hardware'
        legacy = hardware / 'FLStudioMCP'
        folder = (controller_dir or (legacy if (legacy / 'device_FLStudioMCP.py').is_file() else hardware / 'FLStudioCLI')).resolve()
        compatible = (folder / 'device_FLStudioMCP.py').is_file()
        script = folder / ('device_FLStudioMCP.py' if compatible else 'device_FLStudioCLI.py')
        helper = folder / 'flstudio_cli_extension.py'
        data = {'controller': str(script), 'extension': str(helper), 'binding_preserved': compatible,
                'needs_reload': True, 'controller_type': 'FLStudioMCP' if compatible else 'FLStudioCLI'}
        if dry_run:
            data['file_effects'] = []
            emit(Result(command='bridge install-controller', status='planned', data=data)); return
        folder.mkdir(parents=True, exist_ok=True)
        for path in (script, helper):
            backup = path.with_suffix(path.suffix + '.pre-standalone.bak')
            if path.is_file() and not backup.exists(): shutil.copy2(path, backup)
        source = Path(__file__).with_name('controller_base.py').read_text(encoding='utf-8')
        if compatible: source = source.replace('# name=FLStudioCLI', '# name=FLStudioMCP', 1)
        source = source.replace('_CLI_CONTROLLER_DIR = None', '_CLI_CONTROLLER_DIR = ' + repr(str(folder)))
        helper.write_bytes(Path(__file__).with_name('controller_extension.py').read_bytes())
        script.write_text(source, encoding='utf-8')
        emit(Result(command='bridge install-controller', status='artifact_ready', verified_scopes=['controller_files'], data=data))

    @bridge_group.command('install-controller-extension')
    @click.option('--controller-dir', type=click.Path(path_type=Path),
                  default=Path.home() / 'Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP')
    @json_option
    def install_extension(controller_dir):
        """Add global generator parameters to the configured compatible controller."""
        import shutil
        controller_dir = controller_dir.resolve()
        script = controller_dir / 'device_FLStudioMCP.py'
        if not script.is_file():
            raise ValueError('Compatible device_FLStudioMCP.py was not found; specify --controller-dir')
        source = script.read_text(encoding='utf-8-sig')
        marker = '# FLSTUDIO_CLI_EXTENSION'
        helper = controller_dir / 'flstudio_cli_extension.py'
        if marker not in source and '_CLI_FILE_RPC = True' not in source:
            backup = script.with_suffix('.py.pre-cli-extension.bak')
            if not backup.exists():
                shutil.copy2(script, backup)
            source += ('\n\n' + marker + '\nfrom flstudio_cli_extension import install as _install_cli_extension\n'
                       '_install_cli_extension(_HANDLERS, globals())\n')
        source = source.replace('_install_cli_extension(_HANDLERS)\n', '_install_cli_extension(_HANDLERS, globals())\n')
        helper.write_bytes(Path(__file__).with_name('controller_extension.py').read_bytes())
        script.write_text(source, encoding='utf-8')
        emit(Result(command='bridge install-controller-extension', status='artifact_ready',
                    verified_scopes=['controller_files'], data={'controller': str(script), 'extension': str(helper),
                    'needs_reload': True, 'instruction': 'FL Options > Refresh MIDI device list / Update MIDI scripts; no project restart required'}))

    @bridge_group.command('serve')
    @click.option('--port', default=9787, type=click.IntRange(1, 65535))
    @click.option('--midi-out', default='FLStudioMCP RX')
    @click.option('--midi-in', default='FLStudioMCP TX')
    def serve_command(port, midi_out, midi_in):
        serve(port, midi_out, midi_in)

    @bridge_group.command('status')
    @click.option('--port', default=9787, type=click.IntRange(1, 65535))
    @json_option
    def status_command(port):
        data = rpc(port, {'op': 'health'})
        emit(Result(command='bridge status', status='verified', verified_scopes=['bridge_health'], data=data))

    @bridge_group.command('start')
    @click.option('--port', default=9787, type=click.IntRange(1, 65535))
    @json_option
    def start_command(port):
        try:
            data = rpc(port, {'op': 'health'})
        except (ConnectionRefusedError, TimeoutError):
            data = None
        if data is not None:
            if data.get('backend') != BACKEND:
                raise ValueError('This port is owned by another service; migrate it before starting the CLI bridge')
            emit(Result(command='bridge start', status='verified', data=data))
            return
        ensure_windows_midi()
        folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'flstudio-cli'
        folder.mkdir(parents=True, exist_ok=True)
        executable = Path(sys.executable)
        windowless = executable.with_name('pythonw.exe')
        if os.name == 'nt' and windowless.exists():
            executable = windowless
        with (folder / 'bridge.log').open('ab') as log:
            process = subprocess.Popen([str(executable), '-m', 'flstudio_cli', 'bridge', 'serve', '--port', str(port)],
                                       stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'CLI bridge exited during startup; see {folder / "bridge.log"}')
            try:
                data = rpc(port, {'op': 'health'})
                if data.get('backend') == BACKEND:
                    emit(Result(command='bridge start', status='verified', data=data))
                    return
            except (ConnectionRefusedError, TimeoutError):
                pass
            time.sleep(.1)
        raise RuntimeError(f'CLI bridge did not start; see {folder / "bridge.log"}')

    @bridge_group.command('stop')
    @click.option('--port', default=9787, type=click.IntRange(1, 65535))
    @json_option
    def stop_command(port):
        health = rpc(port, {'op': 'health'})
        if health.get('backend') != BACKEND:
            raise ValueError('Refusing to stop a service that is not the CLI MIDI bridge')
        data = rpc(port, {'op': 'shutdown'})
        deadline = time.monotonic() + 4
        while True:
            try:
                current = rpc(port, {'op': 'health'})
                if current.get('pid') != health['pid']:
                    break
            except OSError:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('CLI bridge shutdown is not confirmed')
            time.sleep(.05)
        emit(Result(command='bridge stop', status='verified', data=data))
