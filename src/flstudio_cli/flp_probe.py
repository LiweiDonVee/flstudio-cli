"""Read only the FLhd/FLdt envelope; no score or Playlist event decoding."""

import hashlib
import os
from pathlib import Path
import re
import struct

from .contracts import Result

_HEADER = struct.Struct("<4sIhHH")
_CHUNK = struct.Struct("<4sI")


def _stat_signature(stat: os.stat_result) -> tuple:
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def _producer_version(prefix: bytes, data_length: int) -> tuple[str, str | None]:
    if not prefix or prefix[0] != 199:
        return "unknown", "first_event_is_not_version"
    length = 0
    offset = 1
    # FL variable lengths are bounded to a 32-bit VLQ; never scan later events.
    for index in range(5):
        if offset >= len(prefix):
            return "unknown", "truncated_version_length"
        byte = prefix[offset]
        offset += 1
        if index == 4 and byte > 0x0F:
            return "unknown", "invalid_version_length"
        length |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            if index and byte == 0:
                return "unknown", "noncanonical_version_length"
            break
    else:
        return "unknown", "invalid_version_length"
    if not 1 <= length <= 64 or offset + length > data_length or offset + length > len(prefix):
        return "unknown", "version_payload_out_of_bounds"
    version = prefix[offset:offset + length]
    # Known producer representation is an ASCII dotted four-part version + NUL.
    if not re.fullmatch(rb"[0-9]{1,5}(?:\.[0-9]{1,5}){3}\x00", version):
        return "unknown", "unrecognized_ascii_version"
    return version[:-1].decode("ascii"), None


def probe_flp(path: Path) -> Result:
    source = Path(path).resolve()
    base = {"path": str(source)}
    try:
        before = source.stat()
        digest = hashlib.sha256()
        prefix = bytearray()
        size = 0
        with source.open("rb") as file:
            opened = os.fstat(file.fileno())
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)
                if len(prefix) < 128:
                    prefix.extend(chunk[:128 - len(prefix)])
                size += len(chunk)
            finished = os.fstat(file.fileno())
        try:
            after = source.stat()
        except FileNotFoundError:
            return Result(command="flp probe", status="failed", reason_code="source_changed", data=base)
        # Compare ctime only within the same API: on Windows/Python 3.12
        # path.stat() and fstat() expose different deprecated ctime semantics.
        if (len({_stat_signature(stat) for stat in (before, opened, finished, after)}) != 1
                or before.st_ctime_ns != after.st_ctime_ns
                or opened.st_ctime_ns != finished.st_ctime_ns
                or size != before.st_size):
            return Result(command="flp probe", status="failed", reason_code="source_changed", data=base)
    except OSError as exc:
        return Result(command="flp probe", status="failed", reason_code="source_io_error", data={**base, "message": str(exc)})

    def invalid(message: str) -> Result:
        return Result(command="flp probe", status="failed", reason_code="invalid_flp_container", data={**base, "message": message})

    if size < _HEADER.size + _CHUNK.size:
        return invalid("truncated FLhd or FLdt header")
    magic, header_length, format, channels, ppq = _HEADER.unpack_from(prefix)
    if magic != b"FLhd" or header_length != 6:
        return invalid("expected FLhd with six-byte payload")
    if format not in (0, 1) or ppq == 0:
        return invalid("unsupported header format or zero PPQ")
    data_magic, declared = _CHUNK.unpack_from(prefix, _HEADER.size)
    if data_magic != b"FLdt":
        return invalid("expected FLdt immediately after FLhd")
    actual = size - _HEADER.size - _CHUNK.size
    if declared != actual:
        return invalid("FLdt declared length differs from actual remaining bytes")
    version, version_reason = _producer_version(bytes(prefix[22:]), declared)
    return Result(command="flp probe", status="partial", reason_code="semantic_reader_unavailable",
                  verified_scopes=["flp_container"], data={
                      **base, "size": size, "sha256": digest.hexdigest(),
                      "header": {"format": format, "channel_count": channels, "ppq": ppq},
                      "data_chunk": {"declared_length": declared, "actual_length": actual},
                      "producer_version": version, "producer_version_reason": version_reason,
                      "parse_scope": "container",
                      "semantic_sections": {"notes": "unavailable", "patterns": "unavailable", "playlist": "unavailable"},
                  })
