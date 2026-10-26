"""Files/metadata diagnosis only. Nothing here starts FL or queries its UI."""

import ctypes
from ctypes import wintypes
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import platform
import shutil
import struct
import sys

from . import __version__
from .contracts import Result


def discover_installations() -> list[Path]:
    roots = {Path(value) / "Image-Line" for name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)")
             if (value := os.environ.get(name))}
    if not roots and os.name == "nt":
        roots.add(Path("C:/Program Files/Image-Line"))
    candidates = set()
    for root in roots:
        if root.is_dir():
            for path in root.glob("FL Studio*"):
                if path.is_dir() and (path / "FL64.exe").is_file():
                    candidates.add(path.resolve())
    return sorted(candidates, key=str)


def _file_version(path: Path) -> tuple[str | None, str | None]:
    if os.name != "nt":
        return None, "windows_version_resources_unavailable"

    class FixedInfo(ctypes.Structure):
        _fields_ = [(name, wintypes.DWORD) for name in (
            "signature", "struct_version", "file_version_ms", "file_version_ls",
            "product_version_ms", "product_version_ls", "flags_mask", "flags", "os", "type", "subtype", "date_ms", "date_ls")]

    lib = ctypes.WinDLL("version.dll", use_last_error=True)
    lib.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    lib.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    lib.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
    lib.GetFileVersionInfoW.restype = wintypes.BOOL
    lib.VerQueryValueW.argtypes = [wintypes.LPCVOID, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    lib.VerQueryValueW.restype = wintypes.BOOL
    ignored = wintypes.DWORD()
    size = lib.GetFileVersionInfoSizeW(str(path), ctypes.byref(ignored))
    if not size:
        return None, "no_valid_version_resource"
    buffer = ctypes.create_string_buffer(size)
    if not lib.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None, "version_resource_read_failed"
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not lib.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)) or length.value < ctypes.sizeof(FixedInfo):
        return None, "no_fixed_version_info"
    info = ctypes.cast(pointer, ctypes.POINTER(FixedInfo)).contents
    if info.signature != 0xFEEF04BD:
        return None, "invalid_fixed_version_signature"
    ms, ls = info.file_version_ms, info.file_version_ls
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}", None


def _inspect_file(path: Path) -> dict:
    output = {"path": str(path.resolve()), "exists": path.is_file(), "file_version": None,
              "version_reason": "file_not_found", "sha256": None, "size": None}
    if not output["exists"]:
        return output
    try:
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)
        file_version, reason = _file_version(path)
        after = path.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            output["version_reason"] = "source_changed"
            return output
        output.update(file_version=file_version, version_reason=reason, sha256=digest.hexdigest(), size=after.st_size)
    except OSError as exc:
        output.update(version_reason="file_metadata_unavailable", message=str(exc))
    return output


def inspect_environment(fl_install: Path | None) -> Result:
    invoked = Path(sys.argv[0]).resolve()
    if not invoked.is_file() and os.name == "nt" and invoked.with_suffix(".exe").is_file():
        invoked = invoked.with_suffix(".exe")
    runtime = {"cli_version": __version__, "python_version": platform.python_version(),
               "executable": str(Path(sys.executable).resolve()), "entrypoint": str(invoked) if invoked.is_file() else None,
               "platform": platform.platform(), "bits": struct.calcsize("P") * 8,
               "dependencies": {name: version(name) for name in ("click", "pydantic")}}
    tools = {}
    for name in ("python", "uv", "dotnet"):
        found = shutil.which(name)
        tools[name] = {"path": str(Path(found).resolve()) if found else None,
                       "discovered": found is not None, "version": None, "version_reason": "not_executed"}
    data = {"runtime": runtime, "tools": tools,
            "backends": {name: "not_implemented" for name in ("windows_gui", "official_midi", "fruitylink_native", "flp_semantic")}}
    candidates = discover_installations() if fl_install is None else [Path(fl_install).resolve()]
    if len(candidates) > 1:
        return Result(command="doctor", status="rejected", reason_code="ambiguous_fl_install",
                      data={**data, "candidates": [str(path) for path in candidates]})
    if not candidates:
        data["installation"] = {"path": None, "reason": "not_found", "files": {}}
        return Result(command="doctor", status="partial", reason_code="fl_install_not_found",
                      verified_scopes=["environment_files"], data=data)
    path = candidates[0]
    files = {"fl64": _inspect_file(path / "FL64.exe"), "engine": _inspect_file(path / "FLEngine_x64.dll")}
    data["installation"] = {"path": str(path), "reason": None, "files": files}
    if any(file["version_reason"] == "source_changed" for file in files.values()):
        return Result(command="doctor", status="failed", reason_code="source_changed", data=data)
    complete = all(file["file_version"] is not None and file["sha256"] is not None for file in files.values())
    return Result(command="doctor", status="verified" if complete else "partial",
                  reason_code=None if complete else "fl_install_incomplete",
                  verified_scopes=["environment_files"], data=data)
