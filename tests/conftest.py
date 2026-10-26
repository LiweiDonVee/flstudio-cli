import struct

import pytest


def container_blob(data=None, *, magic=b"FLhd", header_length=6, format=0, channels=5, ppq=96,
                   data_magic=b"FLdt", declared_length=None):
    if data is None:
        version = b"26.1.6.5639\0"
        data = bytes([199, len(version)]) + version
    return (struct.pack("<4sIhHH", magic, header_length, format, channels, ppq)
            + struct.pack("<4sI", data_magic, len(data) if declared_length is None else declared_length)
            + data)


@pytest.fixture
def flp(tmp_path):
    path = tmp_path / "合成工程.flp"
    path.write_bytes(container_blob())
    return path
