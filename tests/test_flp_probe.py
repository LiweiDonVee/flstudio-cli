import hashlib

import pytest

from conftest import container_blob


def test_probe_validates_real_binary_boundaries_without_inventing_semantics(flp):
    from flstudio_cli.flp_probe import probe_flp

    result = probe_flp(flp)
    assert result.status == "partial"
    assert result.reason_code == "semantic_reader_unavailable"
    assert result.verified_scopes == ["flp_container"]
    assert result.data["path"] == str(flp.resolve())
    assert result.data["sha256"] == hashlib.sha256(flp.read_bytes()).hexdigest()
    assert result.data["header"] == {"format": 0, "channel_count": 5, "ppq": 96}
    assert result.data["data_chunk"] == {"declared_length": 14, "actual_length": 14}
    assert result.data["producer_version"] == "26.1.6.5639"
    assert result.data["parse_scope"] == "container"
    assert result.data["semantic_sections"] == {"notes": "unavailable", "patterns": "unavailable", "playlist": "unavailable"}


@pytest.mark.parametrize("blob", [
    b"", b"FLhd", container_blob(magic=b"RIFF"), container_blob(header_length=7),
    container_blob(data_magic=b"oops"), container_blob()[:-1], container_blob() + b"tail",
    container_blob(declared_length=0xFFFFFFFF), container_blob(ppq=0), container_blob(format=2),
])
def test_invalid_containers_fail_instead_of_producing_a_snapshot(tmp_path, blob):
    from flstudio_cli.flp_probe import probe_flp

    path = tmp_path / "invalid.flp"
    path.write_bytes(blob)
    result = probe_flp(path)
    assert result.status == "failed"
    assert result.reason_code == "invalid_flp_container"
    assert result.verified_scopes == []
    assert "sha256" not in result.data


@pytest.mark.parametrize("data", [
    b"\x01\x01random 26.1.6.5639\0", b"", b"\xc7", b"\xc7\x80",
    b"\xc7\x80\x80\x80\x80\x01", b"\xc7\x7f26\0", b"\xc7\x0326\xff",
    b"\xc7\x0326\0", b"\xc7\x043.2x", b"\xc7\x0d26.1.6.5639\0\0",
])
def test_unconfirmed_version_is_unknown_and_does_not_scan_arbitrary_data(tmp_path, data):
    from flstudio_cli.flp_probe import probe_flp

    path = tmp_path / "version.flp"
    path.write_bytes(container_blob(data))
    result = probe_flp(path)
    assert result.status == "partial"
    assert result.data["producer_version"] == "unknown"
    assert result.data["producer_version_reason"]


def test_source_change_during_read_invalidates_the_whole_snapshot(flp, monkeypatch):
    from flstudio_cli import flp_probe

    real_open = type(flp).open

    class ChangingReader:
        def __init__(self, file):
            self.file = file
            self.changed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def __getattr__(self, name):
            return getattr(self.file, name)

        def read(self, *args):
            chunk = self.file.read(*args)
            if not self.changed:
                self.changed = True
                # Simulate a concurrent editor with a real write while the reader is open.
                with real_open(flp, "ab") as writer:
                    writer.write(b"changed")
            return chunk

    def changing_open(path, mode="r", *args, **kwargs):
        file = real_open(path, mode, *args, **kwargs)
        return ChangingReader(file) if path == flp and mode == "rb" else file

    monkeypatch.setattr(type(flp), "open", changing_open)
    result = flp_probe.probe_flp(flp)
    assert result.status == "failed"
    assert result.reason_code == "source_changed"
    assert result.verified_scopes == []
    assert "sha256" not in result.data


def test_stable_rewritten_file_is_not_a_false_concurrent_change(flp):
    from flstudio_cli.flp_probe import probe_flp

    # Windows Python 3.12 path stat and fstat can disagree about deprecated ctime.
    flp.write_bytes(container_blob(channels=7))
    result = probe_flp(flp)
    assert result.status == "partial"
    assert result.data["header"]["channel_count"] == 7


def test_source_disappearing_after_read_is_reported_as_changed(flp, monkeypatch):
    from flstudio_cli.flp_probe import probe_flp

    real_open = type(flp).open

    class RemovedAfterRead:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            return self.file

        def __exit__(self, *args):
            self.file.close()
            flp.unlink()

    def removing_open(path, mode="r", *args, **kwargs):
        file = real_open(path, mode, *args, **kwargs)
        return RemovedAfterRead(file) if path == flp and mode == "rb" else file

    monkeypatch.setattr(type(flp), "open", removing_open)
    result = probe_flp(flp)
    assert result.status == "failed" and result.reason_code == "source_changed"
    assert "sha256" not in result.data
