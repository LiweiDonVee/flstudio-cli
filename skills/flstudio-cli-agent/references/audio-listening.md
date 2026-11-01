# Expressive Sytrus and addressed listening

Requires the CLI development build with `audio preview` and performance maps
(1.3.0.dev0+); detect with `--help` and `sound-design support`. Stable1.2.1 fixes
Automation Clip mute inheritance but does not include these new operations.

## Performance instead of a static preset

In `sytrus_design.operators`, `volume_mappings` edits existing two-point graphs:

```json
{"operator":2,"volume_mappings":[{"source":"velocity","at_min":0.15,"at_max":1}]}
```

For a routed filter, use
`{"filter":1,"cutoff_mappings":[{"source":"mod_x","at_min":0.1,"at_max":0.9}]}`.
Each mapping source is `key`, `velocity`, `mod_x` or `mod_y`. The coordinates are
raw0..1, not Hz/dB. Neutral VOL is1,1; neutral CUT is.5,.5. Set only necessary
maps; multiple maps interact. Existing curve tensions/topology stay intact.

Velocity→modulator VOL changes FM index and spectral response, not just output
gain. Start from a verified FM parent and fixed carrier. Note X/Y→CUT needs an
audible operator→filter route and a useful filter offset. Vary one MIDI input
while fixing the others, then test the actual phrase across pitch/velocity and
inside the arrangement. Do not promise that brightness moves monotonically in
every register. Search `sound-design knowledge --search velocity` or `mod_x`.
Opposite VOL maps (OP1 Mod X1→0, OP2 Mod X0→1) can blend two independently
audible paths. Native overlapping-note endpoints were verified; intermediate
coordinates still need level/timbre calibration, not an equal-power assumption.
Only the validated two Default-family layouts and two-point maps are supported;
arbitrary map topology, random sources and all hidden routes are not.

## Choose the listening object

Write a small JSON request, then:

```powershell
& $fl audio preview --project music.flp --request listen.json --output-dir listen-01
```

- Timbre: `{"scope":"timbre","channel":0}` uses declared short/held test notes.
  Add `notes` for role/register; `processing:"mix"` includes the original route.
- Pattern: `{"scope":"pattern","pattern":1}` includes all Pattern voices.
- Piano Roll: `{"scope":"piano_roll","pattern":1,"channel":0}` addresses
  the actual score, regardless of the focused FL window.
- Mixer: `{"scope":"track","kind":"mixer","track":2}` is post-insert/fader,
  directly to neutral Master. Input/sidechain ancestors remain; downstream buses
  are excluded. Optional `master_fx:true` processes that isolated input.
- Playlist: `{"scope":"track","kind":"playlist","track":1}` keeps native
  placement/controls and control-only other occurrences for sidechains.
- Song: `{"scope":"song"}` preserves the selected arrangement and full mix.

Standalone Pattern/Piano Roll retain Pattern events but omit song Automation
Clips. Add `occurrence:{"clip_index":N}` to hear a native song occurrence.
Channel/Mixer indices start0; Pattern/Playlist tracks start1. Add `arrangement`
if necessary. `--session SESSION` captures unsaved owned-worker changes before
rendering. Do not point at the user's unrelated FL instance.

Use `start_seconds/end_seconds` or unambiguous `start_tick/end_tick` for a small
question. Native playback occurs before cropping, so upstream automation history
is retained. Export latency/PDC/tails still apply. `encoding:"mp3"` creates a
small listening copy while preserving WAV. `--reuse OLD/preview.json` avoids
another native render for a crop/encoding when the prepared state/resources
match. Use a fresh directory after external plugin-managed resource changes.

## DSH actual listening

Both FL presets have `listen_audio`. Pass absolute `preview_manifest` and a
question. For fixed-MIDI candidate preference, pass the matched `comparison.json`
and explicit `artifact_id:"A:context"`, `reference_artifact_id:"B:context"` with
the same file as `reference_manifest`. Solo comparison uses `A:solo/B:solo`.
Do not compare a louder raw candidate against a matched one.

Set `output_file` to a new absolute JSON path in the task directory; the tool
saves its exact receipt. Pass that file directly to `sound-design report
--listening FILE`. Reuse `ready` candidates and verified auditions via `status`;
the listener already checks audio hashes and the report checks native states.
Keep extra reading/experiments focused on an unresolved musical decision.

This tool sends actual audio bytes to a separately configured native audio
model and returns its observations. Attribute them to `listener.model` and
request ID; the current DSH conversation itself did not receive audio.
An aesthetic opinion is not proof of a parameter mechanism or an objective
quality score. Reconcile it with context, repeats and controlled signal tests.

For long songs evaluate sections and track covered intervals. A transmitted
full file is not proof of attention to every moment. If the route is unavailable,
use signal analysis and report `not_performed`; keep audio for later hearing.
Do not install large models or claim hearing from a spectrum.
