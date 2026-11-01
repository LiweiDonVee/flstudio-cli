---
name: flstudio-sound-design
description: Design and revise real FL Studio plugin sounds for a musical role and an actual arrangement using flstudio-cli. Use for delegated sound-design tasks, Sytrus synthesis from init, preset transformation, context auditions, and recoverable candidate delivery.
---

# FL Studio sound-design specialist

Deliver editable native plugin state plus solo and actual-context audio. A useful
candidate has a musical purpose, a distinct synthesis hypothesis, and evidence
that its full saved state survives reopening. Parameter names and host echoes
alone do not establish that evidence.
Requires flstudio-cli 1.2.0+; PCM analysis uses its optional `sound-design` extra.
Performance mappings and addressed previews require 1.3.0.dev0+; inspect actual
`--help` and support rather than assuming an older stable build has them.

## Main-agent handoff

Infer tempo, notes, register, dynamics, plugin and accompaniment from the saved
project. Extract a bounded actual musical excerpt first when the full project is
long. Ask only for intent that would materially change the design. Keep the
user's words and record assumptions rather than turning the task into a form.

```powershell
$fl = Join-Path $env:USERPROFILE '.local\bin\flstudio.exe'
& $fl sound-design support --project excerpt.flp --channel 0
& $fl sound-design prepare --project excerpt.flp --channel 0 --role bass --brief 'Warm but defined bass; leave the kick and lead unchanged' --output-dir sound-work
```

Delegate with this compact instruction, substituting real absolute paths:

> Use $flstudio-sound-design. Read TASK/task.json. Design several substantively
> different candidates for its role, audition solo and in the fixed context,
> revise promising directions, and return RESULT/result.json with the candidate
> ids, evidence paths, recommendation and tradeoffs. Preserve the fixed MIDI and
> all other parts. Operate only your own task branches and private FL workers.

Different agents need different task directories. The CLI serializes concurrent
operations on the same candidate; do not share a live worker between agents.
In the DSH FL Studio preset use `design_sound` with `description`, a complete
`prompt` containing the absolute task/result paths, and optional `cwd`. It selects
the dedicated sound-design preset. Use `send_message` for revisions and
`list_agents` for status; the specialist does not recursively delegate.

## Specialist execution

1. Read `task.json`, then `sound-design support` for the target. The task contains
   actual scores, PPQ, tempo, context, known resources, constraints and budget.
   Use a focused project snapshot or exact `notes list` only if a missing detail
   changes the next decision. Install the `sound-design` extra if PCM analysis
   reports that NumPy is missing; no audio model is required.
2. Query `sound-design knowledge --search WORD` or `--id RECIPE`. These are
   source-attributed design hypotheses with explicit unit/validation rules.
   Load the plugin-specific guide only when needed. Sytrus is the first-choice
   deep adapter; a plugin's mere presence does not mean all its state is writable.
3. Begin with one unchanged init/preset baseline. Explore different mechanisms
   before fine tuning: for example FM-transient body, RM/inharmonic texture,
   subtractive shape/filter, or a different envelope/space strategy. Give each
   branch a new id, description, mechanisms and tradeoffs. Avoid full-parameter
   random searches and near-duplicate candidates.
4. Run `sound-design candidate --task TASK --request CANDIDATE.json`. The CLI
   isolates the edits, observes host values, saves a native FLP, stops the edit
   worker, and reopens in another worker. `ready` requires confirmed parameter
   identities/values and equality of the complete selected sound state.
   `unconfirmed` or `failed` is unresolved: inspect the
   recorded transaction/reopened values, then correct a new branch or resume
   the identical interrupted request. A saved checkpoint is reused on resume.
5. Run `sound-design audition --task TASK --candidate ID`. It renders raw solo,
   actual context, accompaniment, repeated context and reopened context. Inspect
   `audition.json`: silence/timeout/truncation, peak, notes/register, envelope
   occupancy, stereo and contextual band occupancy. These are signal proxies,
   never a musical quality score or proof of psychoacoustic masking.
6. Compare promising branches with `sound-design compare --task TASK
   --candidate A --candidate B --output-dir NEW`. It preserves raw audio and
   writes constant-gain RMS-matched solo/context previews with peak headroom.
   This is an engineering level match, not LUFS or perceived-loudness equality.
   Keep MIDI/render conditions fixed; randomness is observed through repeats.
7. For a specific uncertainty use `audio analyze --purpose pitch|envelope|harmonics|delay|overview`
   and [signal experiment methods](references/analysis.md). Choose a small actual
   interval and controlled reference; do not dump full frame arrays into chat.
   Read `usability`/`reason_code` before interpreting a number. Null/ambiguous
   pitch is not a zero or a measurement to fill in. Use actual listening or an available audio-capable evaluator. If none is
   available, state `listening: not_performed`; recommend only a provisional
   design hypothesis and give the listener matched previews. Do not claim that
   a candidate sounds more natural because its centroid or a model score moved.
8. Revise the promising branch with `parent: "ID"` and a fresh id. Diagnose
   register/rhythm/voicing conflicts before adding more EQ. Do not change other
   parts or the fixed MIDI without explicit authorization.

## Complete states and native UI

The authoritative state is the candidate's `sound.flp`, not a parameter table
or a bounded snapshot. It includes plugin-private state, channel envelopes/host
settings and effect states. Known channel samples are copied when preparing new
tasks. Declare external plugin samples, wavetables or IRs in the request's
`resources`; copying them does not prove that hidden plugin paths were rebound.
Keep plugin versions and resource paths in the result. The full native project
is editable; the WAV is a listening artifact.

When a required control is absent from the host API, inspect the validated
adapter's scope. If native UI is necessary, use only a CLI-owned private worker
and fresh `session screenshot`/receipt before `session input`. `sound-design
capture --task TASK --session SESSION --id NEW --description TEXT --mechanism TEXT`
saves native UI edits and cold-reopens them; it keeps the original worker alive.
Do not treat submitted input or an unvalidated raw offset as success.

## Return, apply, undo and continue

Generate the small handoff with `sound-design report --task TASK --candidate A
--candidate B --recommended A --rationale TEXT --comparison COMPARISON.json
--output RESULT/result.json`. It indexes actual verified states/audio instead
of embedding their catalogs. `--listening FILE` optionally records actual caller
listening evidence; default is `not_performed`.

Return the resulting `result.json` with `task_file`, `candidates` (id, complete FLP,
solo/context raw and matched audio, operation/observation paths), `recommended`,
`reasoning`, `tradeoffs`, `listening` (who/ability/method), `unresolved`,
`resources`, and `reproduce` (exact CLI commands). Evidence and subjective choice
must remain separate. Include unsuccessful hypotheses when they change the next
agent's decision; do not replay an entire log in prose. Point to detailed
observation files instead of embedding full parameter catalogs, repeated signal
arrays or all transactions in the handoff. Start a resumed task with
`sound-design status`; expand the relevant observation file only when needed.
For Sytrus use `design-inspect --summary`, then `--operator N` for details.

The main agent applies a ready candidate to a new project copy:

```powershell
& $fl sound-design apply --task TASK/task.json --candidate ID --project current.flp --output chosen.flp
& $fl sound-design apply --task TASK/task.json --candidate ID --project chosen.flp --output restored.flp --undo
```

Application checks the prior target sound, keeps channel identity/routing,
scores and Playlist, and copies full channel state plus the dedicated insert FX.
Use `--channel-only` when the insert is shared; do not overwrite shared effects.
If the target sound changed meanwhile, prepare a new task instead of bypassing
the precondition. To continue editing the chosen result, prepare a new task from
`chosen.flp` or branch the existing candidate with `parent`.

Read [references/requests.md](references/requests.md) for request/result shapes
and [references/sytrus.md](references/sytrus.md) for actual deep Sytrus operations.
For 3xOsc, Maximus, WaveShaper/Delay3, Edison/Slicex and native Slide/portamento,
read [Producer operations](references/producer-plugins.md) only when needed.
For Sytrus KEY/velocity/Mod X/Y maps or listening to timbre, Pattern, Piano Roll,
track or song, read [expression and native model listening](references/expression-listening.md).
In DSH use the mounted `listen_audio` for actual audio-model observations; both
the main and specialist preset can call it. Record its attribution and coverage.
