import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def cli(*args, env=None, cwd=None, prefix=None):
    proc = subprocess.run([*(prefix or [sys.executable, "-m", "flstudio_cli"]), *map(str, args)],
                          cwd=cwd or ROOT, env=env, capture_output=True, timeout=20)
    stdout = proc.stdout.decode("utf-8")
    assert proc.stderr == b"", proc.stderr.decode("utf-8", errors="replace")
    return proc.returncode, json.loads(stdout)


def write_request(tmp_path, flp):
    payload = dict(operation="notes.replace", project=str(flp), pattern_number=1, channel_index=0,
                   notes=[dict(key=36, start_tick=0, length_tick=24, velocity=100)])
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("args", [("--help",), ("--version",), ("notes", "--help"), ("plan", "--help")])
def test_module_and_console_script_are_json_entrypoints(args):
    for prefix in ([sys.executable, "-m", "flstudio_cli"], [str(Path(sys.executable).with_name("flstudio.exe"))]):
        code, result = cli(*args, prefix=prefix)
        assert code == 0
        assert result["schema_version"] == 1
        assert result["status"] == "verified"
        assert result["data"]


@pytest.mark.parametrize("args,reason", [
    (("nonexistent",), "invalid_arguments"), (("flp", "probe", "--json"), "invalid_arguments"),
    (("notes", "replace", "--pattern-number", "x"), "invalid_arguments"),
])
def test_usage_errors_are_structured_json_with_nonzero_exit(args, reason):
    code, result = cli(*args)
    assert code == 2
    assert result["status"] == "rejected"
    assert result["reason_code"] == reason


def test_doctor_and_probe_run_as_real_processes_without_live_claims(tmp_path, flp):
    code, doctor = cli("doctor", "--fl-install", tmp_path, "--json")
    assert code == 0
    assert doctor["verified_scopes"] == ["environment_files"]
    assert doctor["data"]["installation"]["files"]["fl64"]["exists"] is False
    code, probe = cli("flp", "probe", "--input", flp, "--json")
    assert code == 0
    assert probe["status"] == "partial"
    assert probe["verified_scopes"] == ["flp_container"]
    bad = tmp_path / "bad.flp"
    bad.write_bytes(b"FLhd")
    code, result = cli("flp", "probe", "--input", bad)
    assert code == 5 and result["reason_code"] == "invalid_flp_container"


def test_shared_plan_build_and_notes_dry_run_emit_same_unexecutable_plan(tmp_path, flp):
    request = write_request(tmp_path, flp)
    notes = ROOT / "tests" / "fixtures" / "notes-one.json"
    code, built = cli("plan", "build", "--request", request, "--json")
    assert code == 0
    code, dry_run = cli("notes", "replace", "--project", flp, "--pattern-number", "1", "--channel-index", "0", "--notes", notes, "--dry-run", "--json")
    assert code == 0
    assert built["data"]["plan"] == dry_run["data"]["plan"]
    assert dry_run["data"]["applied_count"] is None
    assert dry_run["data"]["verified_count"] is None
    assert dry_run["data"]["requested_count"] == 1
    assert dry_run["verified_scopes"] == ["flp_container"]
    assert dry_run["data"]["file_effects"] == []


def test_only_explicit_plan_out_writes_and_never_overwrites_input(tmp_path, flp):
    request = write_request(tmp_path, flp)
    output = tmp_path / "计划.json"
    code, result = cli("plan", "build", "--request", request, "--plan-out", output)
    assert code == 0
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert plan == result["data"]["plan"]
    assert plan["executable"] is False
    assert result["data"]["file_effects"] == [{"kind": "plan_file_created", "path": str(output.resolve())}]
    original = flp.read_bytes()
    for target in (flp, request, output):
        before = target.read_bytes()
        code, result = cli("plan", "build", "--request", request, "--plan-out", target)
        assert code == 2 and result["reason_code"] == "plan_output_exists"
        assert target.read_bytes() == before
    assert flp.read_bytes() == original


def test_apply_entrypoints_reject_without_even_loading_files(tmp_path):
    code, result = cli("plan", "apply", "--file", tmp_path / "missing.json", "--json")
    assert code == 7 and result["reason_code"] == "backend_unimplemented"
    code, result = cli("notes", "replace", "--project", tmp_path / "missing.flp", "--pattern-number", 1,
                       "--channel-index", 0, "--notes", tmp_path / "missing.json", "--json")
    assert code == 7 and result["reason_code"] == "backend_unimplemented"
    assert result["data"]["applied_count"] is None
    assert result["verified_scopes"] == []


@pytest.mark.parametrize("raw,path", [
    ('[{"key":NaN,"start_tick":0,"length_tick":24,"velocity":100}]', "$[0].key"),
    ('[{"key":36,"start_tick":0,"length_tick":Infinity,"velocity":100}]', "$[0].length_tick"),
    ('[{"key":true,"start_tick":0,"length_tick":24,"velocity":100}]', "$.notes[0].key"),
    ('[{"key":36,"start_tick":-0.0,"length_tick":24,"velocity":100}]', "$.notes[0].start_tick"),
    ('[{"key":36,"start_tick":0.0,"length_tick":24,"velocity":100}]', "$.notes[0].start_tick"),
    ('[{"key":36,"start_tick":0,"length_tick":24,"velocity":100,"pan":0}]', "$.notes[0].pan"),
])
def test_cli_rejects_bad_notes_with_field_paths_and_no_partial_output(tmp_path, flp, raw, path):
    notes = tmp_path / "notes.json"
    notes.write_text(raw, encoding="utf-8")
    code, result = cli("notes", "replace", "--project", flp, "--pattern-number", 1, "--channel-index", 0,
                       "--notes", notes, "--dry-run")
    assert code == 2 and result["status"] == "rejected"
    assert path in json.dumps(result, ensure_ascii=False)


def test_invalid_filesystem_path_is_still_a_single_json_error():
    # NUL cannot be an argv byte, but an invalid Windows path is representable.
    code, result = cli("flp", "probe", "--input", "bad:\\name.flp")
    assert code != 0
    assert result["status"] in ("failed", "rejected")


def test_capabilities_are_available_through_the_installed_cli():
    code, result = cli("capabilities", "--json")
    assert code == 0
    current = {item["operation"] for item in result["data"]["capabilities"] if item["implemented"]}
    assert current == {"doctor", "flp.container", "plan"}


def test_missing_plan_parent_is_not_created(tmp_path, flp):
    request = write_request(tmp_path, flp)
    output = tmp_path / "not-created" / "plan.json"
    code, result = cli("plan", "build", "--request", request, "--plan-out", output)
    assert code == 5 and result["reason_code"] == "file_io_error"
    assert not output.parent.exists()


def test_excessively_nested_json_is_a_structured_error(tmp_path):
    request = tmp_path / "nested.json"
    request.write_text("[" * 1500 + "0" + "]" * 1500, encoding="utf-8")
    code, result = cli("plan", "build", "--request", request)
    assert code == 2 and result["reason_code"] == "invalid_json"


def test_invalid_oversized_json_integer_is_a_structured_error(tmp_path):
    request = tmp_path / "large-integer.json"
    request.write_text('{"pattern_number":' + '9' * 5000 + '}', encoding="utf-8")
    code, result = cli("plan", "build", "--request", request)
    assert code == 2 and result["reason_code"] == "invalid_json"


def test_unexpected_application_error_is_still_json(monkeypatch, capsys):
    from flstudio_cli import cli as entrypoint

    def fail(**kwargs):
        raise RuntimeError("unexpected read failure")

    monkeypatch.setattr(entrypoint, "app", fail)
    with pytest.raises(SystemExit) as exc:
        entrypoint.main()
    assert exc.value.code == 5
    output = capsys.readouterr()
    assert output.err == ""
    result = json.loads(output.out)
    assert result["status"] == "failed"
    assert result["reason_code"] == "internal_error"


def tree_hash(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def test_dry_run_has_no_process_network_import_or_file_effects(tmp_path, flp):
    # The parent starts the CLI. sitecustomize blocks child execution gateways
    # inside that fresh process before the application is imported.
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text('''
import sys
def deny(event, args):
    if event in {"subprocess.Popen", "os.system", "os.startfile", "os.startfile/2", "os.posix_spawn", "os.spawn"} or event.startswith("socket."):
        raise RuntimeError("forbidden gateway: " + event)
    if event == "import" and any(part in str(args[0]).lower() for part in ("flstudio_mcp", "rtmidi", "winreg", "pywinauto", "pyautogui")):
        raise RuntimeError("forbidden import: " + str(args[0]))
sys.addaudithook(deny)
''', encoding="utf-8")
    # Seed representative user scripts and logs; any write changes the tree.
    user = tmp_path / "user"
    for directory in ("home", "appdata", "localappdata", "state", "scripts", "logs"):
        (user / directory).mkdir(parents=True)
        (user / directory / "sentinel.txt").write_text("保持不变", encoding="utf-8")
    request = write_request(tmp_path, flp)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
           "PYTHONPATH": str(guard), "HOME": str(user / "home"), "USERPROFILE": str(user / "home"),
           "APPDATA": str(user / "appdata"), "LOCALAPPDATA": str(user / "localappdata"),
           "XDG_STATE_HOME": str(user / "state")}
    before = tree_hash(tmp_path)
    code, result = cli("plan", "build", "--request", request, env=env, cwd=tmp_path)
    assert code == 0 and result["status"] == "planned"
    notes = ROOT / "tests" / "fixtures" / "notes-one.json"
    code, result = cli("notes", "replace", "--project", flp, "--pattern-number", 1, "--channel-index", 0,
                       "--notes", notes, "--dry-run", env=env, cwd=tmp_path)
    assert code == 0 and result["data"]["plan"]["executable"] is False
    assert tree_hash(tmp_path) == before
