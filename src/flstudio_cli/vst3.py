"""Register installed VST3 modules through FL's own Plugin Manager CLI."""
from __future__ import annotations

import ctypes as c
from pathlib import Path
import uuid


def module_info(path: Path) -> dict:
    path = path.resolve()
    if path.is_dir() and path.suffix.casefold() == '.vst3':
        matches = list((path / 'Contents/x86_64-win').glob('*.vst3'))
        if len(matches) != 1:
            raise ValueError('VST3 bundle must contain one x86_64-win module')
        path = matches[0]
    if not path.is_file() or path.suffix.casefold() != '.vst3':
        raise ValueError('Choose an installed Windows x64 .vst3 module or bundle')
    dll = c.WinDLL(str(path))
    if hasattr(dll, 'InitDll'):
        dll.InitDll.restype = c.c_bool
        if not dll.InitDll():
            raise ValueError('VST3 InitDll rejected initialization')
    dll.GetPluginFactory.restype = c.c_void_p
    factory = dll.GetPluginFactory()
    if not factory:
        raise ValueError('VST3 GetPluginFactory returned no factory')
    table = c.cast(factory, c.POINTER(c.POINTER(c.c_void_p))).contents
    def method(slot, returns, *args):
        return c.CFUNCTYPE(returns, c.c_void_p, *args)(table[slot])
    class FactoryInfo(c.Structure):
        _fields_ = [('vendor', c.c_char * 64), ('url', c.c_char * 256), ('email', c.c_char * 128), ('flags', c.c_int32)]
    class ClassInfo(c.Structure):
        _fields_ = [('cid', c.c_ubyte * 16), ('cardinality', c.c_int32),
                    ('category', c.c_char * 32), ('name', c.c_char * 64)]
    try:
        vendor = FactoryInfo()
        method(3, c.c_int32, c.POINTER(FactoryInfo))(factory, c.byref(vendor))
        count = method(4, c.c_int32)(factory)
        classes = []
        for index in range(count):
            info = ClassInfo()
            code = method(5, c.c_int32, c.c_int32, c.POINTER(ClassInfo))(factory, index, c.byref(info))
            if code == 0 and info.category == b'Audio Module Class':
                classes.append({'name': info.name.decode('utf-8'),
                                'guid': '{' + str(uuid.UUID(bytes_le=bytes(info.cid))).upper() + '}'})
        return {'module': str(path), 'vendor': vendor.vendor.decode('utf-8'), 'classes': classes}
    finally:
        method(2, c.c_uint32)(factory)


def register_plugin(path: Path, kind: str, install: Path, name=None, dry_run=False):
    from .native import run_fl
    data = module_info(path)
    matches = [item for item in data['classes'] if name is None or item['name'] == name]
    if len(matches) != 1:
        raise ValueError('Choose --name to identify exactly one VST3 audio class')
    plugin = matches[0]
    if Path(plugin['name']).name != plugin['name'] or any(x in plugin['name'] for x in '/\\'):
        raise ValueError('Plugin class name is not a safe FL preset filename')
    database = Path.home() / 'Documents/Image-Line/FL Studio/Presets/Plugin database'
    preset = database / 'Installed' / ('Generators' if kind == 'generator' else 'Effects') / 'VST3' / (plugin['name'] + '.fst')
    data.update(plugin=plugin, preset=str(preset), live_applied=False)
    if dry_run:
        data.update(status='planned', file_effects=[], applied_count=None)
        return data
    if preset.exists():
        # Preserve a user's customized preset; registration is only necessary
        # for a new plugin, not for loading an existing FST.
        raise ValueError(f'Plugin is already registered; use the existing preset: {preset}')
    args = ['-flpath', str(install.resolve()), '-add', '-name', plugin['name'], '-format', 'vst3',
            '-type', 'synth' if kind == 'generator' else 'effect', '-filename', data['module'],
            '-vendor', data['vendor'], '-guid', plugin['guid']]
    process = run_fl(install / 'System/Tools/Plugin Manager/PluginManager.exe', args, path.resolve().parent, timeout=15)
    nfo = preset.with_suffix('.nfo')
    if not preset.is_file() or not nfo.is_file():
        return {**data, 'status': 'failed', 'process': process, 'reason': 'plugin_registration_not_confirmed'}
    config = nfo.read_text(encoding='utf-8-sig')
    if plugin['guid'] not in config or data['module'] not in config:
        raise ValueError('Plugin Manager output does not identify the requested module/class')
    return {**data, 'status': 'artifact_ready', 'process': process,
            'scope': 'FL-generated preset and database entry; load/render verifies audio separately'}


def register(group, emit, json_option):
    import click
    from .contracts import Result
    @group.command('register-vst3')
    @click.option('--file', 'path', required=True, type=click.Path(path_type=Path))
    @click.option('--kind', required=True, type=click.Choice(['generator', 'effect']))
    @click.option('--name')
    @click.option('--fl-install', default=Path('C:/Program Files/Image-Line/FL Studio 2026'), type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def register_command(path, kind, name, fl_install, dry_run):
        if dry_run:
            # Loading a plugin module itself runs its initialization code.
            # A preview therefore does not even inspect its factory.
            emit(Result(command='plugin register-vst3', status='planned',
                        data={'module': str(path.resolve()), 'kind': kind, 'file_effects': [], 'module_loaded': False}))
            return
        data = register_plugin(path, kind, fl_install, name)
        emit(Result(command='plugin register-vst3', status=data['status'], reason_code=data.get('reason'),
                    verified_scopes=['registered_plugin_files'] if data['status'] == 'artifact_ready' else [], data=data))
