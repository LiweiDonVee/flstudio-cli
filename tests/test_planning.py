import hashlib

import pytest


def request_for(path):
    from flstudio_cli.contracts import NotesReplaceRequest

    return NotesReplaceRequest.model_validate(dict(operation="notes.replace", project=str(path),
                                                  pattern_number=1, channel_index=0,
                                                  notes=[dict(key=36, start_tick=0, length_tick=24, velocity=100)]))


def test_plan_is_deterministic_and_keeps_unresolved_selectors_and_unknown_counts(flp):
    from flstudio_cli.flp_probe import probe_flp
    from flstudio_cli.json_output import canonical_json
    from flstudio_cli.planning import build_plan

    request = request_for(flp)
    before = flp.read_bytes()
    plan = build_plan(request, probe_flp(flp))
    assert canonical_json(plan) == canonical_json(build_plan(request, probe_flp(flp)))
    assert plan.executable is False
    assert plan.target_resolution == "unresolved_selectors"
    assert plan.bound_target is None
    assert set(plan.unmet_requirements) == {"score.semantic_read", "target.resolve", "notes.replace", "project.persistence_verify"}
    assert plan.source_sha256 == hashlib.sha256(before).hexdigest()
    assert plan.requested_count == 1
    assert plan.artifact_count is None and plan.applied_count is None and plan.verified_count is None
    assert flp.read_bytes() == before


def test_plan_rejects_missing_unverified_or_wrong_source_evidence(flp, tmp_path):
    from flstudio_cli.contracts import Result
    from flstudio_cli.flp_probe import probe_flp
    from flstudio_cli.planning import PlanningError, build_plan

    request = request_for(flp)
    for result in [Result(command="flp probe", status="failed"),
                   Result(command="flp probe", status="partial", data={"path": str(flp), "sha256": "a" * 64}),
                   probe_flp(tmp_path / "missing.flp")]:
        with pytest.raises(PlanningError):
            build_plan(request, result)
    other = tmp_path / "other.flp"
    other.write_bytes(flp.read_bytes())
    with pytest.raises(PlanningError):
        build_plan(request, probe_flp(other))


def test_capabilities_do_not_upgrade_external_evidence_to_implemented_live_support():
    from flstudio_cli.capabilities import list_capabilities

    capabilities = list_capabilities()
    by_operation = {item["operation"]: item for item in capabilities}
    assert {key for key, item in by_operation.items() if item["implemented"]} == {"doctor", "flp.container", "plan"}
    for key in ("notes.read", "notes.replace", "pattern", "playlist", "mixer", "plugin", "automation", "project.save", "render.wav"):
        item = by_operation[key]
        assert item["implemented"] is False
        assert item["availability"] == "not_implemented"
        assert item["verification_level"] == "source_only"
        assert item["last_evidence"] is None
    assert by_operation["notes.replace"]["external_evidence"]


def test_builder_uses_only_supplied_observations_without_filesystem_resolution(flp, monkeypatch):
    from pathlib import Path
    from flstudio_cli.flp_probe import probe_flp
    from flstudio_cli.planning import build_plan

    request, snapshot = request_for(flp), probe_flp(flp)

    def forbidden(*args, **kwargs):
        raise AssertionError("pure planning must not touch the filesystem")

    with monkeypatch.context() as guard:
        guard.setattr(Path, "resolve", forbidden)
        guard.setattr(Path, "stat", forbidden)
        guard.setattr(Path, "open", forbidden)
        plan = build_plan(request, snapshot)
    assert plan.requested_count == 1
    assert plan.source_sha256 == snapshot.data["sha256"]
    assert plan.bound_target is None
