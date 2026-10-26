import hashlib
from pathlib import Path


def test_missing_installation_is_a_completed_files_only_diagnosis(tmp_path, monkeypatch):
    from flstudio_cli import environment

    monkeypatch.setattr(environment, "discover_installations", lambda: [])
    result = environment.inspect_environment(None)
    assert result.status == "partial"
    assert result.reason_code == "fl_install_not_found"
    assert result.verified_scopes == ["environment_files"]
    assert result.data["installation"]["path"] is None
    assert result.data["runtime"]["executable"] == str(Path(__import__("sys").executable).resolve())
    assert all(value == "not_implemented" for value in result.data["backends"].values())


def test_partial_install_and_invalid_version_resources_are_reported_without_execution(tmp_path):
    from flstudio_cli.environment import inspect_environment

    (tmp_path / "FL64.exe").write_bytes(b"not executable")
    result = inspect_environment(tmp_path)
    files = result.data["installation"]["files"]
    assert files["fl64"]["exists"] is True
    assert files["fl64"]["file_version"] is None
    assert files["fl64"]["version_reason"]
    assert files["fl64"]["sha256"] == hashlib.sha256(b"not executable").hexdigest()
    assert files["engine"]["exists"] is False
    assert files["engine"]["file_version"] is None
    assert result.status == "partial"
    assert result.verified_scopes == ["environment_files"]


def test_doctor_resolves_the_actual_windows_console_launcher(tmp_path, monkeypatch):
    import sys
    from flstudio_cli.environment import inspect_environment

    script = tmp_path / "flstudio.exe"
    script.write_bytes(b"test launcher; never executed")
    monkeypatch.setattr(sys, "argv", [str(script.with_suffix("")), "doctor"])
    result = inspect_environment(tmp_path)
    assert result.data["runtime"]["entrypoint"] == str(script.resolve())


def test_multiple_installations_require_selection_instead_of_guessing(tmp_path, monkeypatch):
    from flstudio_cli import environment

    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    monkeypatch.setattr(environment, "discover_installations", lambda: [one, two])
    result = environment.inspect_environment(None)
    assert result.status == "rejected"
    assert result.reason_code == "ambiguous_fl_install"
    assert result.data["candidates"] == [str(one.resolve()), str(two.resolve())]
    assert environment.inspect_environment(two).data["installation"]["path"] == str(two.resolve())


def test_install_discovery_checks_only_expected_directory_entries(tmp_path, monkeypatch):
    from flstudio_cli import environment

    root = tmp_path / "Image-Line"
    for name in ("FL Studio 2026", "FL Studio 2025", "Shared", "FL Studio ASIO"):
        (root / name).mkdir(parents=True)
    for name in ("FL Studio 2026", "FL Studio 2025", "Shared"):
        (root / name / "FL64.exe").write_bytes(b"placeholder")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    paths = environment.discover_installations()
    assert paths == [(root / "FL Studio 2025").resolve(), (root / "FL Studio 2026").resolve()]
