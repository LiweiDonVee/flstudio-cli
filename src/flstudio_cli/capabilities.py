"""Current implementation and outside research are separate evidence columns."""

from .contracts import Capability


def list_capabilities() -> list[dict]:
    implemented = [
        Capability(operation="doctor", implemented=True, availability="available", verification_level="offline_fixture",
                   backend="filesystem", limitations=["File metadata and PATH discovery only; no running FL inspection"],
                   last_evidence='docs/m0-verification.md'),
        Capability(operation="flp.container", implemented=True, availability="available", verification_level="offline_fixture",
                   backend="filesystem", limitations=["FLhd/FLdt envelope only; notes, patterns and playlist unavailable"],
                   last_evidence='docs/m0-verification.md'),
        Capability(operation="plan", implemented=True, availability="available", verification_level="offline_fixture",
                   backend='pure_planner', limitations=['Saved-score plans require an explicit new output path; no live editor writes'],
                   last_evidence='tests/test_workflows.py'),
    ]
    for operation, scope, backend in [
        ('project.build', 'saved_channels,saved_notes,saved_playlist', 'flp_file'),
        ('project.inspect', 'saved_channels,saved_notes,saved_playlist,saved_mixer', 'flp_file'),
        ('notes.read', 'saved_notes', 'flp_file'), ('notes.replace', 'saved_notes', 'flp_file'),
        ('pattern', 'saved_notes', 'flp_file'), ('playlist', 'saved_playlist', 'flp_file'),
        ('mixer', 'saved_mixer', 'flp_file'), ('sample.load', 'saved_channels', 'flp_file'),
        ('plugin.load_preset', 'saved_plugin_state', 'flp_file'),
        ('project.save_copy', 'saved_project', 'flp_file'),
        ('render.wav', 'fl_engine_export,pcm_audio', 'fl_native_batch'),
    ]:
        implemented.append(Capability(operation=operation, implemented=True, availability='available',
                                      verification_level='audio' if operation == 'render.wav' else 'persistence',
                                      backend=backend, profile='FL 26.1.6.5639 / factory Basic',
                                      limitations=['Saved-project copies; does not modify the open editor',
                                                   'Fresh fixed-layout Playlist clips; unknown edited layouts are rejected'],
                                      last_evidence='docs/release-0.2.md: ' + scope))
    external = {
        'live.attach': 'Not integrated; file edits never pretend to change the open editor',
        'plugin.arbitrary_ui': 'Native plugin UI controls without a file-state profile remain GUI operations',
        "automation": "R6: external native linear-clip subset",
    }
    for operation, evidence in external.items():
        implemented.append(Capability(operation=operation, implemented=False, availability="not_implemented",
                                      verification_level="source_only", backend=None,
                                      limitations=['No implementation for this operation; see docs/coverage.md'],
                                      external_evidence=[f"docs/research.md: {evidence}"]))
    return [item.model_dump(mode="python") for item in implemented]
