"""Measured workflows and remaining gaps, without treating raw API reach as coverage."""
from .contracts import Capability


def list_capabilities() -> list[dict]:
    result = []
    def add(operation, level, backend, limitations=(), evidence='docs/fullstack.md', implemented=True, requires_desktop=None):
        if requires_desktop is None:
            requires_desktop = backend in {'fl_native_batch', 'addressed_controller', 'midi_sysex', 'owned_window_messages', 'owned_piano_script', 'owned_controller_deadlines'}
        result.append(Capability(operation=operation, implemented=implemented,
            availability='available' if implemented else 'not_implemented',
            verification_level=level, backend=backend, profile='FL 26.1.6.5639',
            requires_desktop=requires_desktop,
            limitations=list(limitations), last_evidence=evidence).model_dump(mode='python'))

    add('doctor', 'offline_fixture', 'filesystem', ['File metadata and PATH discovery; no running FL inspection'], 'docs/m0-verification.md')
    add('flp.container', 'offline_fixture', 'filesystem', ['Envelope-only quick check; project inspect decodes objects'], 'docs/m0-verification.md')
    add('plan', 'offline_fixture', 'pure_planner', ['Explicit new output path; saved-score plans do not write to a live editor'], 'tests/test_workflows.py')
    for operation in ('project.build', 'project.inspect', 'notes.read', 'notes.replace', 'pattern', 'playlist',
                      'mixer', 'sample.load', 'plugin.load_preset', 'project.save_copy'):
        add(operation, 'persistence', 'flp_file', ['Saved-project copies; source files are preserved',
            'Detected record layouts; ambiguous or unsupported layouts are rejected'])
    add('render.wav', 'audio', 'fl_native_batch', ['Owned process and new PCM WAV; native export settings still apply'])
    add('plugin.saved_param', 'persistence', 'flp_file', ['Saved profiles: Emphasizer, Sytrus, EQ2, Reeverb2, Soft Clipper, Limiter',
        'Unknown preset values stay null; raw native and normalized live units differ'], 'docs/sytrus-mixing.md')
    for operation in ('plugin.preset_list', 'sytrus.host_controls', 'mixer.send_levels'):
        add(operation, 'persistence' if operation == 'plugin.preset_list' else 'audio', 'flp_file',
            ['Saved project copies; per-profile units remain explicit'], 'docs/sytrus-mixing.md')
    add('mixer.fx_chains', 'audio', 'flp_file', ['Linked effect identities follow unambiguous copy_from moves',
        'Linked deletion/replacement or ambiguous copies are rejected before edits'])
    add('automation', 'audio', 'flp_file', ['FL-authored template required for new links; existing curves retain raw flags',
        'Native target checks: tempo, channel/Mixer volume, Surge XT generator, Fruity Balance effect'])
    add('playlist.audio_cuts_gain', 'audio', 'flp_file', ['Audio windows use milliseconds; Pattern windows ticks and Automation windows beats'])
    add('project.fields', 'persistence', 'flp_file', ['Field availability follows the saved layout; raw native units stay explicit'])
    add('notes.transform_clone', 'persistence', 'flp_file', ['Saved scores, not live Piano Roll; articulation and unselected records retained'])
    add('project.diff_merge', 'persistence', 'flp_file', ['Three-way merge covers Playlist; conflicting non-Playlist changes are rejected'])
    add('project.markers_timing', 'audio', 'flp_file', ['Linear/hold tempo integration; nonlinear/overlap or Pattern tempo events report unknown timing'])
    add('session.owned', 'persistence', 'addressed_controller', ['Separate FL process/Desktop with a loaded controller; source file is preserved'])
    for operation in ('live.status', 'live.set_tempo', 'live.set_mixer_pan', 'live.plugin_params', 'live.set_plugin_param', 'live.query', 'live.apply'):
        add(operation, 'live', 'addressed_controller', ['Loaded standalone controller, or optional compatible MIDI transport',
            'Writes require readback; they do not save the project'])
    add('live.generator_params', 'audio', 'addressed_controller', ['Global channel indices; host-exposed parameters only'])
    add('live.plugin_transaction', 'audio', 'addressed_controller', ['Up to 32 writes with host readback and conditional restoration',
        'Host normalized values do not certify canonical plugin values or persistence'])
    add('session.plugin_persistence', 'persistence', 'addressed_controller', ['Explicit owned checkpoint and separate reopen worker',
        'Numeric expectations checked against reopened values; original worker continues'])
    add('project.plugin_identity', 'persistence', 'flp_file', ['Wrapper name/vendor/module path and raw class-ID bytes; plugin state remains opaque'])
    add('project.validate', 'offline_fixture', 'flp_file', ['Read-only structural and semantic checks; does not run FL or certify private plugin state'], 'docs/fullstack.md')
    add('project.snapshot', 'offline_fixture', 'flp_file', ['Bounded context output; omitted sections are explicit and can be requested independently'], 'docs/fullstack.md')
    add('project.snapshot_delta', 'offline_fixture', 'flp_file', ['Baseline files are immutable; equal only covers comparable sections, while omitted sections remain unknown'], 'docs/fullstack.md')
    add('audio.inspect', 'offline_fixture', 'filesystem', ['Decoded PCM levels include aggregate and per-channel peak/RMS dBFS; no LUFS or true-peak claim'], 'docs/commands.md', requires_desktop=False)
    add('plugin.saved_settings', 'persistence', 'flp_file', ['Common Wrapper flags; known small native plugin raw fields and Notebook 2 Unicode pages',
        'VST MIDI/processing settings are read-only; unknown state bytes are retained'])
    add('session.ui', 'persistence', 'owned_window_messages', ['Private CLI-owned workers only; screenshots must be inspected before addressed input',
        'Keys and canvas pointer input; FL popup menus require keyboard navigation; effects need independent verification'])
    add('live.piano_roll', 'audio', 'owned_piano_script', ['Explicit Pattern/global channel; named dispatcher, exact before-score precondition and native save verification',
        'Agent executes the captured script menu; selected flags are transient across FL reopen'])
    add('live.automation_record', 'audio', 'owned_controller_deadlines', ['Actual Pattern event recording for tempo/channel/Mixer/generator/FX targets',
        'First-use recording modal requires observed input; OnIdle scheduling is not sample-accurate; cancelled events remain'])
    add('mixer.create_tracks', 'persistence', 'owned_window_messages', ['Prepare, observed Insert/Move-right menu actions, then verify original routes/state and native save'])
    add('playlist.audio_fades', 'persistence', 'owned_window_messages', ['Observed FL26 canvas fade handles and native save readback; no generic offline fade-tail writer'])
    add('live.public_api', 'live', 'addressed_controller', ['API return values do not certify arbitrary write semantics'])
    add('bridge.lifecycle', 'live', 'midi_sysex', ['Optional relay; configured ports and a compatible controller required'], 'docs/release-0.4.1.md')
    add('plugin.verify', 'audio', 'fl_native_batch', ['Controlled-input verifier for Emphasizer v2 Emphasis; copied effect, not the open editor'], 'docs/release-0.4.md')
    for operation, limitation in (
        ('live.native_attach', 'Native injection is not integrated; addressed controller sessions are available'),
        ('plugin.arbitrary_ui', 'Controls absent from the host parameter API require GUI handling'),
    ):
        add(operation, 'source_only', None, [limitation], implemented=False)
    return result
