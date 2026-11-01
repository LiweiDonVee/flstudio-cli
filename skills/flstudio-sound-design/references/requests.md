# Concrete requests and result contract

The current CLI help and `sound-design support` take precedence over stale
examples. Run `sound-design status --task TASK` to resume an interrupted handoff.

## Optional task constraints

Pass `--constraints constraints.json` to prepare only when these data are known:

```json
{
  "harmony": "C minor; the lead occupies C4-Bb5",
  "reference_description": "Intimate and rounded, with a defined attack",
  "avoid": ["kick low octave", "long tails across rests"],
  "must_preserve": ["all notes", "drums", "master chain"],
  "plugins": ["Sytrus", "Surge XT"],
  "max_candidates": 6,
  "max_render_seconds": 45,
  "render_timeout_seconds": 90
}
```

The task extracts notes, register, tempo, velocities and accompaniment. Do not ask
the user to re-enter them. Keep latency requirements in `latency_requirement`;
native render wall time is not an estimate of real-time audio latency.

## A generic hosted candidate

```json
{
  "id": "slow-attack",
  "description": "A softer pad onset, retaining the existing oscillator state",
  "mechanisms": ["amplifier envelope timing"],
  "params": [
    {"param": "A Amp EG Attack", "value": 0.42},
    {"param": "A Amp EG Release", "value": 0.4}
  ],
  "tradeoffs": ["May lose short-note definition; compare the actual chord rhythm"]
}
```

These names/values were tested with the installed Surge XT profile. The values
are normalized host controls, not seconds. `candidate` records display units
after cold reopening; a new plugin/version must be discovered again. `parent`
can select an existing ready candidate for a revision. `plugin_preset` accepts
an installed FST as a starting point, not a claim that it has been redesigned.

Additional candidate sections are `sytrus` (existing integer host overrides),
`sytrus_design` (the validated deep Sytrus schema), `channel_volume_raw` (the
same raw level field as project editing), `channel_settings` (existing grouped
envelope/polyphony/filter settings),
`fx_chain` (complete target-insert slots), `effect_params` (slot/param/value or
value_raw), and `resources` (existing external files to retain). Only the target
channel and its exclusive insert may change. See the native Sytrus guide for
matrix direction, raw ranges, and supported envelope layouts.

## Result

```json
{
  "task_file": "ABSOLUTE/task.json",
  "candidates": [
    {"id":"slow-attack","project":"ABSOLUTE/sound.flp","solo":"ABSOLUTE/solo.wav","context":"ABSOLUTE/context-1.wav","evidence":"ABSOLUTE/audition.json"}
  ],
  "recommended": "slow-attack",
  "reasoning": "Provisional envelope hypothesis for a background role",
  "tradeoffs": ["Attack may be too slow on short chords"],
  "listening": {"status":"not_performed","method":"signal analysis only"},
  "unresolved": ["Subjective contextual preference"],
  "resources": [],
  "reproduce": ["flstudio sound-design audition --task ABSOLUTE/task.json --candidate slow-attack"]
}
```

The full comparison contains all preview paths/gains. Technical viability,
semantic request satisfaction and musical preference are separate conclusions.
