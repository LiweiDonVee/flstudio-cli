"""Current implementation and outside research are separate evidence columns."""

from .contracts import Capability


def list_capabilities() -> list[dict]:
    implemented = [
        Capability(operation="doctor", implemented=True, availability="available", verification_level="offline_fixture",
                   backend="filesystem", limitations=["File metadata and PATH discovery only; no running FL inspection"],
                   last_evidence="tests/test_environment.py; tests/test_cli.py"),
        Capability(operation="flp.container", implemented=True, availability="available", verification_level="offline_fixture",
                   backend="filesystem", limitations=["FLhd/FLdt envelope only; notes, patterns and playlist unavailable"],
                   last_evidence="tests/test_flp_probe.py; tests/test_cli.py"),
        Capability(operation="plan", implemented=True, availability="available", verification_level="offline_fixture",
                   backend="pure_planner", limitations=["Unresolved selectors; executable=false; no apply backend"],
                   last_evidence="tests/test_planning.py; tests/test_cli.py"),
    ]
    external = {
        "notes.read": "R1/R3/R6/R7: external API/file-reader candidates; not integrated",
        "notes.replace": "R1/R6: old MIDI artifacts/native API evidence; no new CLI live verification",
        "pattern": "R3/R6: external MIDI/native interfaces",
        "playlist": "R6/R7: external native/file interfaces with format limitations",
        "mixer": "R1/R3/R6: external API observations",
        "plugin": "R1/R3/R6: external parameter and state observations",
        "automation": "R6: external native linear-clip subset",
        "project.save": "R6: external save APIs; no persistence evidence for this CLI",
        "render.wav": "R3: documented FL batch options; no audio evidence for this CLI",
    }
    for operation, evidence in external.items():
        implemented.append(Capability(operation=operation, implemented=False, availability="not_implemented",
                                      verification_level="source_only", backend=None,
                                      limitations=["No execution backend in M0; see docs/coverage.md"],
                                      external_evidence=[f"docs/research.md: {evidence}"]))
    return [item.model_dump(mode="python") for item in implemented]
