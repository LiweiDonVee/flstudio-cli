"""Run FL's own exporter in an owned private Windows desktop.

No keyboard injection, attached input queues, or user-window automation. The
existing editor can remain open. Only the process created here is terminated
on an export timeout; the input FLP is never written by this module.
"""
from __future__ import annotations

import array
import ctypes as c
from ctypes import wintypes as w
import hashlib
import math
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import wave


class Startup(c.Structure):
    _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR),
                ('title', w.LPWSTR), ('x', w.DWORD), ('y', w.DWORD), ('width', w.DWORD),
                ('height', w.DWORD), ('xchars', w.DWORD), ('ychars', w.DWORD),
                ('fill', w.DWORD), ('flags', w.DWORD), ('show', w.WORD),
                ('reserved_size', w.WORD), ('reserved_ptr', c.c_void_p),
                ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]


class ProcessInfo(c.Structure):
    _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]


def run_fl(executable: Path, arguments: list[str], workdir: Path, timeout=120) -> dict:
    kernel = c.WinDLL('kernel32', use_last_error=True)
    user = c.WinDLL('user32', use_last_error=True)
    user.CreateDesktopW.argtypes = [w.LPCWSTR, w.LPCWSTR, c.c_void_p, w.DWORD, w.DWORD, c.c_void_p]
    user.CreateDesktopW.restype = w.HANDLE
    user.CloseDesktop.argtypes = [w.HANDLE]
    kernel.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL,
                                     w.DWORD, c.c_void_p, w.LPCWSTR, c.POINTER(Startup), c.POINTER(ProcessInfo)]
    kernel.CreateProcessW.restype = w.BOOL
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.WaitForSingleObject.restype = w.DWORD
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
    kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    name = 'flstudio_cli_' + uuid.uuid4().hex
    desktop = user.CreateDesktopW(name, None, None, 0, 0x01FF, None)
    if not desktop:
        raise c.WinError(c.get_last_error())
    startup = Startup()
    startup.cb, startup.desktop, startup.flags, startup.show = c.sizeof(startup), name, 1, 0
    process = ProcessInfo()
    command = c.create_unicode_buffer(subprocess.list2cmdline([str(executable), *arguments]))
    start = time.monotonic()
    try:
        if not kernel.CreateProcessW(str(executable), command, None, None, False, 0, None,
                                     str(workdir), c.byref(startup), c.byref(process)):
            raise c.WinError(c.get_last_error())
        state = kernel.WaitForSingleObject(process.process, max(1, round(timeout * 1000)))
        if state == 258:
            kernel.TerminateProcess(process.process, 1)
            kernel.WaitForSingleObject(process.process, 5000)
            return {'pid': process.pid, 'status': 'timeout', 'exit_code': None,
                    'elapsed_seconds': round(time.monotonic() - start, 3)}
        if state != 0:
            raise c.WinError(c.get_last_error())
        code = w.DWORD()
        if not kernel.GetExitCodeProcess(process.process, c.byref(code)):
            raise c.WinError(c.get_last_error())
        return {'pid': process.pid, 'status': 'exited', 'exit_code': code.value,
                'elapsed_seconds': round(time.monotonic() - start, 3)}
    finally:
        if process.thread:
            kernel.CloseHandle(process.thread)
        if process.process:
            kernel.CloseHandle(process.process)
        user.CloseDesktop(desktop)


def read_audio(path: Path) -> tuple[dict, list[float]]:
    with wave.open(str(path), 'rb') as audio:
        channels, width, rate, frames = audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getnframes()
        raw = audio.readframes(frames)
    if width not in (1, 2, 3, 4) or len(raw) != frames * channels * width:
        raise ValueError('Unsupported or truncated PCM output')
    if width == 1:
        values = [(value - 128) / 128 for value in raw]
    elif width in (2, 4):
        values = [x / (2 ** (width * 8 - 1)) for x in array.array('h' if width == 2 else 'i', raw)]
    else:
        values = [int.from_bytes(raw[i:i + 3], 'little', signed=True) / 8388608 for i in range(0, len(raw), 3)]
    peak = max(map(abs, values), default=0.0)
    rms = math.sqrt(sum(value * value for value in values) / max(1, len(values)))
    return {'sample_rate': rate, 'channels': channels, 'sample_width': width, 'frames': frames,
            'duration_seconds': frames / rate, 'peak': peak, 'rms': rms,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}, values


def render(project: Path, output: Path, install: Path, timeout=120, allow_silence=False) -> dict:
    project, output, install = project.resolve(), output.resolve(), install.resolve()
    if output.suffix.lower() != '.wav' or output.exists():
        raise ValueError('Choose a new .wav output path')
    if not project.is_file() or not output.parent.is_dir():
        raise ValueError('Input project and output parent must exist')
    executable = install / 'FL64.exe'
    if not executable.is_file():
        raise ValueError('FL64.exe was not found in the installation')
    before = hashlib.sha256(project.read_bytes()).hexdigest()
    from .flp import Project
    doc = Project.read(project)
    doc._replace_value(9, b'\x01')
    # Export a temporary Song-mode copy in the same folder so relative sample
    # paths retain their base, without modifying the user's saved mode/selection.
    with tempfile.NamedTemporaryFile(prefix='.flstudio-render-', suffix='.flp', dir=project.parent, delete=False) as temporary:
        temporary.write(doc.encode())
        render_input = Path(temporary.name)
    try:
        process = run_fl(executable, ['/R' + str(output), '/Ewav', str(render_input)], output.parent, timeout)
    finally:
        render_input.unlink()
    if process['status'] != 'exited' or process['exit_code'] != 0 or not output.is_file():
        return {'status': 'failed', 'reason': 'fl_export_failed', 'process': process,
                'output': str(output), 'input_sha256': before}
    after = hashlib.sha256(project.read_bytes()).hexdigest()
    if before != after:
        return {'status': 'unknown', 'reason': 'source_changed_during_render', 'process': process}
    metadata, _ = read_audio(output)
    patterns = doc.patterns()
    ticks_per_bar = doc.ppq * 4
    end_tick = 0
    expected_notes = 0
    for clip in doc.playlist():
        pattern = patterns.get(clip['pattern_number'])
        if pattern and pattern['notes']:
            expected_notes += len(pattern['notes'])
            source_end = max(n['start_tick'] + n['length_tick'] for n in pattern['notes'])
            source_span = math.ceil(source_end / ticks_per_bar) * ticks_per_bar
            end_tick = max(end_tick, clip['start_tick'] + min(clip['length_tick'], source_span))
    expected_seconds = end_tick * 60 / (doc.tempo * doc.ppq)
    if (expected_notes and metadata['peak'] == 0 and not allow_silence) or metadata['duration_seconds'] + .05 < expected_seconds:
        return {'status': 'failed', 'reason': 'render_content_mismatch', 'process': process,
                'output': str(output), 'audio': metadata, 'expected_minimum_seconds': expected_seconds,
                'message': 'Silent or truncated FL output; exporter exit 0 is not composition success'}
    return {'status': 'verified', 'backend': 'fl_native_batch', 'render_mode': 'song', 'process': process,
            'input': str(project), 'input_sha256': before, 'output': str(output),
            'audio': metadata, 'expected_minimum_seconds': expected_seconds, 'input_unchanged': True}
