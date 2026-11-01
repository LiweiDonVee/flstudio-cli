# Agent plugin sound design

The main Agent can delegate one musical role in a real FL excerpt, receive
several editable sounds and solo/context auditions, apply a choice, undo it,
and hand it back for revision. Sytrus is the primary deep adapter; the generic
host path was separately exercised with Surge XT.

Install with `uv tool install --editable ".[sound-design]"`. The extra adds
NumPy for small PCM/STFT observations, not an audio model. FL Studio, plugins,
licenses and the CLI controller remain local requirements. Prepare a saved,
bounded excerpt of the actual music; the default limit is 45 seconds.

## Main Agent

```powershell
$fl = Join-Path $env:USERPROFILE '.local\bin\flstudio.exe'
& $fl sound-design support --project excerpt.flp --channel 0
& $fl sound-design prepare --project excerpt.flp --channel 0 --role bass --brief 'Warm defined bass; preserve kick and lead' --output-dir sound-work
```

`prepare` extracts exact notes, velocities, PPQ/BPM and context; it retains the
source and copies known channel samples. Optional constraints include harmony,
reference description/audio, sounds to avoid, allowed plugins, latency intent
and budgets. Record reasonable assumptions instead of asking a long questionnaire.
The saved excerpt is authoritative, rather than unsaved GUI contents.

Give a specialist the absolute task path, result destination and any intent not
already in the task. Load [flstudio-sound-design](../../skills/flstudio-sound-design/SKILL.md).
In the DSH FL Studio preset the tool call is:

```json
{
  "description": "Design bass for excerpt",
  "cwd": "ABSOLUTE/work-directory",
  "prompt": "Read the flstudio-sound-design Skill and ABSOLUTE/sound-work/task.json. Explore distinct synthesis directions within its budget, render solo and in its fixed context, revise promising directions, and write ABSOLUTE/sound-work/result.json with complete states, auditions, recommendation, tradeoffs and evidence. Preserve all notes and other parts."
}
```

Call `design_sound` with that object. Its fixed destination is the
`fl-studio-sound-designer` preset. Use `send_message` for feedback and
`list_agents` when status changes the next decision. A child starts with its
self-contained task rather than the parent's whole conversation. Separate
children need separate task directories; a candidate has an OS lock, but that
does not make a shared plugin window safe for several agents.

## Specialist

1. Read the task and support declaration; query only relevant parameter names
   or `sound-design knowledge --search WORD`. Distinguish documented controls,
   actual readback, rendered effect and complete-state restoration.
2. Keep an unchanged reference. Explore synthesis, envelope, modulation or space
   directions with different musical purposes, then refine promising branches.
3. Run `candidate`, `audition`, then `compare`. Host values are normalized;
   physical display units are separate. Discrete values can canonicalize only
   after reopening. Never convert a Hz/ms request to an assumed linear 0..1 value.
4. Diagnose clashes in register, attacks, note length, release, dynamics and space
   using the actual accompaniment. If the cause is orchestration, report it;
   do not silently change other parts or erase character with corrective EQ.
5. Return the complete native FLP, resources, raw and matched auditions,
   operation/observation paths, rationale, tradeoffs and unresolved judgments.

```powershell
& $fl sound-design candidate --task sound-work/task.json --request examples/sound-design/sytrus-fm-bass.json
& $fl sound-design audition --task sound-work/task.json --candidate fm-transient-bass-active
# After creating another ready candidate:
& $fl sound-design compare --task sound-work/task.json --candidate fm-transient-bass-active --candidate OTHER --output-dir comparison
```

A request combines `id`, `description`, `mechanisms`, optional `parent`,
`plugin_preset`, host `params`, `sytrus_design`, existing `sytrus` host controls,
`channel_volume_raw`, `channel_settings`, dedicated `fx_chain`/`effect_params`,
`resources` and `tradeoffs`. Names and exact schema are in the
[Skill reference](../../skills/flstudio-sound-design/references/requests.md).
Deep Sytrus examples are in [examples/sound-design](../../examples/sound-design).

`candidate` saves natively, stops its edit worker, cold-reopens in another
private worker, reads requested values and compares the complete selected
sound state. `ready` is technical evidence, not a taste judgment. A new
`parent` branch retains the previous checkpoint. `--resume` accepts an identical
interrupted request, stops its exact old owned worker, and reuses a saved
checkpoint or restarts the edit from its parent. Existing outputs are preserved.

For long iterations use `sound-design status --task TASK`: it returns a compact
brief, identity, budgets, branch descriptions, audio state and paths. Full
parameter/transaction/signal arrays remain on disk and are marked omitted.
`sytrus design-inspect --summary` and repeated `--operator N` let an Agent
expand only the next relevant part instead of rereading the whole instrument.
`sound-design report --task TASK --candidate A --candidate B --recommended A
--rationale TEXT --comparison COMPARISON.json --output result.json` generates
the compact handoff from verified artifacts. It retains detailed evidence paths
instead of duplicating all metrics, parameters and operation history. Optional
`--listening FILE` records who/method; it is caller evidence, not a CLI hearing claim.

`audition` renders context repeats, solo, accompaniment and the reopened state.
It retains raw PCM, estimates within-state variability, and reports the actual
engineering tolerances used for the reopened comparison. Short variable tails
are padded only during analysis. Context occupancy and preview matching use the
fixed musical duration; longer raw release tails are retained. `compare` makes
constant-gain PCM-RMS previews with common peak headroom. This is neither LUFS
nor guaranteed perceived-loudness equality.

If a necessary hidden control needs native UI, use a CLI-owned private session,
inspect a fresh screenshot, operate it, then `sound-design capture`. Capture
saves the native edit, checks a separate native baseline for context pollution,
and cold-reopens the result. It keeps the original editing worker alive.
Tempo, other parts and shared effects cannot be silently changed by a capture.

## Apply, undo, continue

```powershell
& $fl sound-design apply --task sound-work/task.json --candidate ID --project current.flp --output chosen.flp
& $fl sound-design apply --task sound-work/task.json --candidate ID --project chosen.flp --output restored.flp --undo
& $fl sound-design prepare --project chosen.flp --channel 0 --role bass --brief 'Keep its identity; shorten release' --output-dir revision
```

Application resolves the target IID even after channel reordering, checks its
previous sound, retains the receiving channel's name/routing/identity and all
musical content, and copies full channel state and exclusive-insert effects.
For a shared insert use `--channel-only`. If the target changed since the task,
prepare a new task. Undo restores sound state; byte order of unrelated control
records can differ while semantic state remains equal. The user's live editor
is not modified by saved-file operations.

External plugin samples/wavetables/IRs must be declared. The CLI preserves opaque
state and copies declared files, but cannot prove every hidden path was rebound.
Do not claim arbitrary-plugin coverage or portability from a parameter table.

See [support matrix](support-matrix.md), [real evidence](validation.md),
[deep Sytrus scope](sytrus.md) and [knowledge sources](sources.json).
