"""Window observations and addressed key messages for explicitly owned FL workers."""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib


def _png(width, height, bgrx):
    """Encode the captured RGB pixels using the standard PNG container."""
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgrx[2::4], bgrx[1::4], bgrx[0::4]
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    stride = width * 3
    rows = b''.join(b'\0' + rgb[y * stride:(y + 1) * stride] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 3)) + chunk(b'IEND', b''))


def _binding(session):
    from .sessions import process_stamp
    if not str(session.get('owner_marker', '')).startswith('__FLCLI_OWNED__:'):
        raise ValueError('Window observation requires an explicitly owned session')
    if process_stamp(session['pid']) != session['process_created']:
        raise ValueError('Owned process has exited or changed')
    state = json.loads((Path(session['rpc_directory']) / (session['rpc_prefix'] + 'state.json')).read_text(encoding='utf-8'))
    if any(state.get(a) != session[b] for a, b in
           (('pid', 'pid'), ('instance', 'controller_instance'), ('owner_marker', 'owner_marker'))):
        raise ValueError('Owned controller binding changed')
    return state


def _child(payload):
    try:
        run = subprocess.run([sys.executable, '-m', 'flstudio_cli.owned_ui'],
            input=json.dumps(payload), capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Owned window operation timed out; FL was left running. Observe before retrying input.') from None
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or 'Owned window operation failed')
    return json.loads(run.stdout)


def observe(session, output=None, window=None, children=False):
    """Bound PrintWindow in a short-lived process; a timeout never closes FL."""
    if output is not None and (output.exists() or not output.parent.is_dir()):
        raise ValueError('Choose a new BMP file with an existing parent')
    if output is not None and output.suffix.lower() not in ('.bmp', '.png'):
        raise ValueError('Owned screenshots support .png or .bmp')
    return _child({'session': session, 'output': str(output.resolve()) if output is not None else None,
                   'window': window, 'children': children})


def _observe(session, output, window, children=False):
    state = _binding(session)
    from .sessions import process_stamp
    u, g = c.WinDLL('user32', use_last_error=True), c.WinDLL('gdi32', use_last_error=True)
    u.SetThreadDpiAwarenessContext.argtypes = [w.HANDLE]
    u.SetThreadDpiAwarenessContext.restype = w.HANDLE
    u.SetThreadDpiAwarenessContext(w.HANDLE(-4))
    u.OpenDesktopW.argtypes = [w.LPCWSTR, w.DWORD, w.BOOL, w.DWORD]; u.OpenDesktopW.restype = w.HANDLE
    u.CloseDesktop.argtypes = [w.HANDLE]
    u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
    u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
    u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
    u.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
    u.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
    u.ClientToScreen.argtypes = [w.HWND, c.POINTER(w.POINT)]
    u.GetWindow.argtypes = [w.HWND, w.UINT]; u.GetWindow.restype = w.HWND
    u.GetParent.argtypes = [w.HWND]; u.GetParent.restype = w.HWND
    u.IsWindowVisible.argtypes = [w.HWND]
    u.GetDpiForWindow.argtypes = [w.HWND]; u.GetDpiForWindow.restype = w.UINT
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    items, desktop = [], None

    def inspect(hwnd, _):
        pid = w.DWORD(); thread = u.GetWindowThreadProcessId(hwnd, c.byref(pid))
        if pid.value == session['pid']:
            title, kind, rect = c.create_unicode_buffer(1024), c.create_unicode_buffer(256), w.RECT()
            u.GetWindowTextW(hwnd, title, len(title)); u.GetClassNameW(hwnd, kind, len(kind))
            if u.GetWindowRect(hwnd, c.byref(rect)):
                client, origin = w.RECT(), w.POINT()
                u.GetClientRect(hwnd, c.byref(client)); u.ClientToScreen(hwnd, c.byref(origin))
                items.append({'hwnd': int(hwnd), 'title': title.value, 'class': kind.value, 'thread': thread,
                    'parent': int(u.GetParent(hwnd) or 0),
                    'visible': bool(u.IsWindowVisible(hwnd)), 'owner': int(u.GetWindow(hwnd, 4) or 0),
                    'rect': [rect.left, rect.top, rect.right, rect.bottom], 'dpi': u.GetDpiForWindow(hwnd),
                    'client_rect': [client.left, client.top, client.right, client.bottom], 'client_origin': [origin.x, origin.y]})
        return True

    try:
        if session.get('desktop_mode') == 'interactive':
            u.EnumWindows.argtypes = [callback_type, w.LPARAM]
            if not u.EnumWindows(callback_type(inspect), 0): raise c.WinError(c.get_last_error())
        else:
            # Keep this handle open through capture: releasing it after enumeration
            # makes a private desktop's otherwise valid HWND unusable for GetWindowDC.
            desktop = u.OpenDesktopW(session['desktop'], 0, False, 0x41)
            if not desktop: raise c.WinError(c.get_last_error())
            u.EnumDesktopWindows.argtypes = [w.HANDLE, callback_type, w.LPARAM]
            if not u.EnumDesktopWindows(desktop, callback_type(inspect), 0): raise c.WinError(c.get_last_error())
        if children or (window is not None and not any(i['hwnd'] == window for i in items)):
            roots = [i['hwnd'] for i in items if i['visible']]
            known = {i['hwnd'] for i in items}
            def child(hwnd, parameter):
                if hwnd not in known and u.IsWindowVisible(hwnd):
                    inspect(hwnd, parameter); known.add(hwnd)
                return True
            u.EnumChildWindows.argtypes = [w.HWND, callback_type, w.LPARAM]
            for root in roots: u.EnumChildWindows(root, callback_type(child), 0)
        _binding(session)
        data = {'pid': session['pid'], 'controller_state_age_seconds': time.time() - state['ts'],
                'process_created': session['process_created'], 'controller_instance': session['controller_instance'],
                'owner_marker': session['owner_marker'], 'observed_at': time.time(),
                'project_binding_freshly_queried': False, 'windows': items}
        if output is None: return data
        selected = [i for i in items if i['hwnd'] == window] if window is not None else [
            i for i in items if not i['owner'] and i['title'].endswith('FL Studio 2026')]
        if len(selected) != 1:
            raise ValueError('Choose exactly one owned HWND from session windows')
        item = selected[0]; hwnd = item['hwnd']
        pid = w.DWORD(); u.GetWindowThreadProcessId(hwnd, c.byref(pid))
        if pid.value != session['pid']: raise ValueError('Window changed ownership before capture')
        width, height = item['rect'][2] - item['rect'][0], item['rect'][3] - item['rect'][1]
        if not 0 < width <= 10000 or not 0 < height <= 10000:
            raise ValueError('Window has no capturable rectangle')
        u.GetWindowDC.argtypes = [w.HWND]; u.GetWindowDC.restype = w.HDC
        u.ReleaseDC.argtypes = [w.HWND, w.HDC]
        u.PrintWindow.argtypes = [w.HWND, w.HDC, w.UINT]
        g.CreateCompatibleDC.argtypes = [w.HDC]; g.CreateCompatibleDC.restype = w.HDC
        g.CreateDIBSection.argtypes = [w.HDC, c.c_void_p, w.UINT, c.POINTER(c.c_void_p), w.HANDLE, w.DWORD]
        g.CreateDIBSection.restype = w.HBITMAP
        g.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]; g.SelectObject.restype = w.HGDIOBJ
        g.DeleteObject.argtypes = [w.HGDIOBJ]; g.DeleteDC.argtypes = [w.HDC]
        dc, mem, bitmap, previous = None, None, None, None
        try:
            dc = u.GetWindowDC(hwnd)
            if not dc: raise c.WinError(c.get_last_error())
            mem = g.CreateCompatibleDC(dc)
            if not mem: raise c.WinError(c.get_last_error())
            header = struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 32, 0, width * height * 4, 0, 0, 0, 0)
            info, bits = c.create_string_buffer(header), c.c_void_p()
            bitmap = g.CreateDIBSection(dc, info, 0, c.byref(bits), None, 0)
            if not bitmap or not bits.value: raise c.WinError(c.get_last_error())
            previous = g.SelectObject(mem, bitmap)
            if not previous or previous == c.c_void_p(-1).value: raise c.WinError(c.get_last_error())
            began = time.monotonic()
            if not u.PrintWindow(hwnd, mem, 2): raise RuntimeError('FL did not paint the requested window')
            g.GdiFlush()
            u.GetWindowThreadProcessId(hwnd, c.byref(pid))
            if pid.value != session['pid'] or process_stamp(session['pid']) != session['process_created']:
                raise ValueError('Owned process or window changed during capture')
            pixels = c.string_at(bits, width * height * 4)
            with Path(output).open('xb') as stream:
                stream.write(_png(width, height, pixels) if Path(output).suffix.lower() == '.png' else
                    struct.pack('<2sIHHI', b'BM', 54 + len(pixels), 0, 0, 54) + header + pixels)
            data.update(window=item, output=output, capture_seconds=time.monotonic() - began,
                        pixel_content_verified=False, print_window_flags=2)
            data.pop('windows')
            return data
        finally:
            if previous: g.SelectObject(mem, previous)
            if bitmap: g.DeleteObject(bitmap)
            if mem: g.DeleteDC(mem)
            if dc: u.ReleaseDC(hwnd, dc)
    finally:
        if desktop: u.CloseDesktop(desktop)


KEYS = {'enter': 13, 'escape': 27, 'up': 38, 'down': 40, 'left': 37, 'right': 39,
        'home': 36, 'end': 35, 'tab': 9, 'space': 32, 'backspace': 8, 'delete': 46, 'f7': 118}


def submit_key(session, observation, key):
    if key not in KEYS: raise ValueError('Choose an explicitly supported key')
    return _child({'operation': 'key', 'session': session, 'observation': observation, 'key': key})


def submit_pointer(session, observation, action):
    if set(action) not in ({'move'}, {'click'}, {'drag'}): raise ValueError('Choose one move, click or drag')
    return _child({'operation': 'pointer', 'session': session, 'observation': observation, 'pointer': action})


def _submit_key(session, observation, key=None, pointer=None):
    if session.get('desktop_mode') != 'private':
        raise ValueError('Native key input is restricted to CLI-owned private desktops')
    _binding(session)
    if any(observation.get(k) != session[k] for k in ('pid', 'process_created', 'controller_instance', 'owner_marker')):
        raise ValueError('Screenshot belongs to a different owned session')
    if 'output' not in observation: raise ValueError('Input requires a window screenshot receipt')
    expected = observation['window']
    # Enumeration must happen in this input process, as well as the capture
    # process, before Windows maps handles from the private desktop.
    u = c.WinDLL('user32', use_last_error=True)
    u.SetThreadDpiAwarenessContext.argtypes = [w.HANDLE]; u.SetThreadDpiAwarenessContext.restype = w.HANDLE
    u.SetThreadDpiAwarenessContext(w.HANDLE(-4))
    u.OpenDesktopW.argtypes = [w.LPCWSTR, w.DWORD, w.BOOL, w.DWORD]; u.OpenDesktopW.restype = w.HANDLE
    u.CloseDesktop.argtypes = [w.HANDLE]
    u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
    u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
    u.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
    u.IsWindowVisible.argtypes = [w.HWND]
    u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    u.MapVirtualKeyW.argtypes = [w.UINT, w.UINT]
    u.ScreenToClient.argtypes = [w.HWND, c.POINTER(w.POINT)]
    u.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
    u.ChildWindowFromPointEx.argtypes = [w.HWND, w.POINT, w.UINT]
    u.ChildWindowFromPointEx.restype = w.HWND
    callback = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    u.EnumDesktopWindows.argtypes = [w.HANDLE, callback, w.LPARAM]
    u.EnumChildWindows.argtypes = [w.HWND, callback, w.LPARAM]
    desktop = u.OpenDesktopW(session['desktop'], 0, False, 0x41)
    if not desktop: raise c.WinError(c.get_last_error())
    try:
        found, roots = [], []
        def inspect(hwnd, _):
            pid = w.DWORD(); u.GetWindowThreadProcessId(hwnd, c.byref(pid))
            if pid.value == session['pid']:
                roots.append(hwnd)
                if hwnd == expected['hwnd']: found.append(hwnd)
            return True
        u.EnumDesktopWindows(desktop, callback(inspect), 0)
        if not found:
            for root in list(roots): u.EnumChildWindows(root, callback(inspect), 0)
        if len(found) != 1: raise ValueError('Captured window is no longer on the owned desktop')
        hwnd, rect, kind = found[0], w.RECT(), c.create_unicode_buffer(256)
        u.GetWindowRect(hwnd, c.byref(rect)); u.GetClassNameW(hwnd, kind, len(kind))
        if (kind.value != expected['class'] or not u.IsWindowVisible(hwnd) or
                [rect.left, rect.top, rect.right, rect.bottom] != expected['rect']):
            raise ValueError('Captured window identity or geometry changed; observe again')
        _binding(session)
        route = [hwnd]
        if pointer is None:
            vk = KEYS[key]; scan = u.MapVirtualKeyW(vk, 0)
            flags = 1 | (scan << 16) | (0x1000000 if key in ('left', 'right', 'up', 'down', 'home', 'end', 'delete') else 0)
            messages = [(0x100, vk, flags), (0x101, vk, flags | 0xc0000000)]
        else:
            if 'popup' in kind.value.casefold(): raise ValueError('Use captured keyboard navigation for FL popup menus; pointer activation is not reliable')
            action, points = next(iter(pointer.items()))
            points = points if action == 'drag' else [points]
            if len(points) != (2 if action == 'drag' else 1) or any(len(p) != 2 or any(type(v) is not int for v in p) for p in points): raise ValueError('Window pixel coordinates must be integer pairs')
            client_points = []
            for x, y in points:
                point, client = w.POINT(rect.left + x, rect.top + y), w.RECT()
                if not u.ScreenToClient(hwnd, c.byref(point)) or not u.GetClientRect(hwnd, c.byref(client)): raise c.WinError(c.get_last_error())
                if not 0 <= point.x < client.right or not 0 <= point.y < client.bottom: raise ValueError('Pointer must stay inside the captured client area')
                client_points.append(point)
            point = client_points[0]
            for _ in range(16):
                child = u.ChildWindowFromPointEx(hwnd, point, 7)
                if not child or child == hwnd: break
                pid = w.DWORD(); u.GetWindowThreadProcessId(child, c.byref(pid))
                if pid.value != session['pid']: raise ValueError('Pointer route left the owned process')
                hwnd = child; route.append(hwnd)
                point = w.POINT(rect.left + points[0][0], rect.top + points[0][1])
                if not u.ScreenToClient(hwnd, c.byref(point)): raise c.WinError(c.get_last_error())
            def packed(p):
                if not 0 <= p.x <= 32767 or not 0 <= p.y <= 32767: raise ValueError('Client coordinates exceed Windows message range')
                return p.x | (p.y << 16)
            position = packed(point)
            messages = [(0x200, 0, position)]
            if action in ('click', 'drag'): messages.append((0x201, 1, position))
            if action == 'drag':
                end = w.POINT(rect.left + points[1][0], rect.top + points[1][1]); client = w.RECT()
                if not u.ScreenToClient(hwnd, c.byref(end)) or not u.GetClientRect(hwnd, c.byref(client)): raise c.WinError(c.get_last_error())
                if not 0 <= end.x < client.right or not 0 <= end.y < client.bottom: raise ValueError('Drag leaves its owned child control')
                for i in range(1, 11):
                    step = w.POINT(round(point.x + (end.x - point.x) * i / 10), round(point.y + (end.y - point.y) * i / 10))
                    messages.append((0x200, 1, packed(step)))
                messages.append((0x202, 0, packed(end)))
            elif action == 'click': messages.append((0x202, 0, position))
        for message, parameter, position in messages:
            if not u.PostMessageW(hwnd, message, parameter, position): raise c.WinError(c.get_last_error())
        return {'submitted': True, 'effect_verified': False, 'window': hwnd, 'key': key, 'pointer': pointer, 'route': route,
                'observation_time': observation['observed_at'], 'global_input_used': False}
    finally:
        u.CloseDesktop(desktop)


if __name__ == '__main__':
    try:
        request = json.loads(sys.stdin.read())
        operation = request.pop('operation', 'observe')
        print(json.dumps(_submit_key(**request) if operation in ('key', 'pointer') else _observe(**request)))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
