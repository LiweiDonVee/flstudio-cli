# Fullstack implementation — 1.0.3

This branch expands FL project operations against the reference projects in
the supplied integration note. It is not a claim of complete GUI coverage or
a completed comparison against every reference. Tested native host:
FL Studio Producer 26.1.6.5639, MIDI scripting 45, Windows x64.

## Fast deployment

```powershell
uv tool install --editable . --python 3.12
flstudio bridge install-controller
flstudio live query --command cli_capabilities
```

Reload MIDI scripts in FL after installation. An existing `FLStudioMCP`
controller binding is preserved by name; its implementation is standalone.
On a new machine, bind `FLStudioCLI` to an available MIDI Input once. The
controller's `OnIdle` then services file requests without a MIDI relay or MCP.
The expected revision is `flstudio-cli-fullstack-6`. Installing files alone
does not confirm that FL loaded them.

`live` discovers one fresh editor endpoint and binds to it. Use `--editor-pid`
when several editors are active. A request never falls back to another
transport after an addressed file request fails.

Before handing a file to FL, run the read-only structural preflight:

```powershell
flstudio project validate --input result.flp
```

It checks the FL envelope, decoded channel and note identities, Playlist record references, Mixer routes, Automation controller links, and a parser encode round-trip. A verified result is a saved-project integrity result; it does not claim private plugin-state compatibility on an unknown FL build.

For long-running work, request a bounded context instead of the full project dump:

```powershell
flstudio project snapshot --input result.flp --focus channels --focus mixer --budget 12000
flstudio project snapshot --input result.flp --focus playlist --detail --limit 16
```

The response always keeps the project fingerprint and counts. `context.focus`, `context.omitted` and `context.budget_exceeded` make the current visibility explicit, so an Agent can expand one section in the next turn without re-reading everything.
Save a baseline when a session is going to span several turns, then ask only for the delta:

```powershell
flstudio project snapshot --input result.flp --focus project --focus mixer --output state.json
flstudio project snapshot --input result.flp --focus project --focus mixer --since state.json
```

`delta.equal` means the comparable sections did not change. `delta.complete` is false when either baseline omitted a section; that keeps an omitted area from being mistaken for an unchanged area.


For repeated read-only inspection, select only the sections an Agent needs:

```powershell
flstudio project inspect --input source.flp --summary `
  --section channels --section patterns --section arrangements
```

This path keeps the executable startup small and avoids loading live-control
and Pydantic command registrations. It still parses the same FLP event stream;
`--summary` omits individual note objects. The full command tree loads when a
write, live session, render, or other command runs.

For work that should leave the user's editor alone:

```powershell
flstudio session start --project source.flp --output-dir private-work
flstudio live --session private-work/session.json status
flstudio session save --session private-work/session.json --output result.flp
flstudio session stop --session private-work/session.json
```

The session owns a separate process/Desktop and a working copy. Save obtains
FL's actual saved FLP and removes the reserved ownership marker in the output.
Zero-channel projects use a temporary project-title marker. Sources and
existing output paths are never overwritten.

## Project editing

| Commands | Operations |
| --- | --- |
| `project inspect`, `metadata`, `channel-settings`, `arrangements`, `controllers` | Metadata/time/meter, sampler processing, envelopes/LFO, arp/polyphony/stretch fields, track properties, full Pattern controller records; wrapped plugin name/vendor/path/class-ID bytes |
| `notes list/replace/transform` | Explicit Pattern/channel scores; transpose, shift, scale, quantize, reverse, invert, seeded humanize, note articulation fields |
| `project edit` | Combined edits; clone channels/Patterns, remap copied score/controllers, retain unknown event data |
| `plugin settings` | Common Wrapper flags, VST MIDI/processing reads, known small native plugin raw fields, Notebook 2 Unicode pages |
| `playlist list/edit` | Per-record layout, pattern/audio/automation clips, move/length/group/mute/duplicate/delete; audio source cuts in milliseconds and clip gain |
| `automation list/edit/create` | Existing point containers and interpolation flags; new linked Automation channels using an installed FL-authored template |
| `project markers` | Arrangement/Pattern scope; signature markers and elapsed seconds with linear/hold tempo automation |
| `project diff/merge` | Semantic differences and conservative three-way Playlist merge; conflicts produce no merged file |
| `render wav` | FL-native Song export, completed-file checks, decoded PCM, expected duration where calculable |

Build/edit schemas remain in [quickstart](quickstart-0.2.md) and
[Sytrus and mixing](sytrus-mixing.md). Additional `project edit` sections are
`metadata`, `arrangements`, `controllers`, `transforms`, `markers`, `playlist_edits`
and `automation`, `plugin_settings`. Consult command help for selectors; Pattern numbers start
at 1, global channel/Mixer/slot indices at 0, Playlist tracks at 1.

Automation creation request example:

```json
{
  "name": "Volume gate",
  "target": {"kind": "channel_volume", "channel": 0},
  "points": [
    {"position_beats": 0, "value": 0},
    {"position_beats": 2, "value": 1, "curve": "hold"},
    {"position_beats": 4, "value": 1, "curve": "hold"}
  ],
  "track": 2, "start_tick": 0, "length_tick": 384
}
```

Pass it to `automation create --project source.flp --request curve.json
--output automated.flp`. Point positions are beats; placement uses the file's
PPQ ticks. Native validation covers channel volume, Mixer volume, tempo,
Surge XT generator volume and a moved Fruity Balance parameter. Other target
profiles have explicit address models but require their own native validation.
Nonlinear curves are stored without pretending their duration is linear.

## Third-party plugin parameters

```powershell
flstudio live --session private-work/session.json plugin-find --channel 0 --search Volume
flstudio live --session private-work/session.json plugin-apply --channel 0 --request parameters.json
```

`parameters.json` is an array of up to 32 changes:

```json
[{"param":"Global Volume","value":0.83,"expect":1.0}]
```

Select a generator with `--channel`, or an effect with `--track` and `--slot`.
Only parameters exposed by FL are addressable. Exact names must identify one
index; duplicate names require the index. Continuous values are normalized
0..1. Discrete controls can quantize requests and fail exact confirmation.

The controller snapshots, writes and independently reads back each value.
Failure/cancellation restores only values still attributable to this
operation; uncertain state is reported. Its scope is `host_readback`, including
restoration; `persistence_verified` is false. FL can echo an arbitrary requested
number for a discrete parameter even when the plugin has quantized it. The
public API exposes no reliable step count; parameter types remain unknown.
Transaction results omit a purported settled display value: FL's display text
can lag its numeric echo. Use an explicit read or reopened observation for text.
A successful live write does not save the project. Native validation used two Surge XT instances, 20 parameters,
instance isolation, failed quantized writes, cancellation, save/reopen and
actual audio changes. Surge XT is a test plugin, not a runtime dependency.

For explicit persistence observation or numeric assertions, stop the owned
transport and finish pending parameter jobs, then run:

```powershell
flstudio session verify-params --session private-work/session.json --request checks.json --output-dir checked
```

```json
[{"channel":0,"params":[{"param":12},{"param":14,"expect":0.335}]}]
```

This saves a new checkpoint, opens a separate verification worker, checks
plugin identity/count/parameter names, reads values, then closes that worker.
The original worker continues. No `expect` means observation only; an explicit
numeric mismatch returns `failed/persisted_value_mismatch`. Unavailable reads
or changed bindings return `unknown`. Display equality is reported separately
and does not certify semantic equivalence. A Surge Scene Mode request of
0.37123 was independently observed as 0.335 after reopening; this operation
now distinguishes those values without calling the original write persisted.

At zero channel/Mixer volume, `vol_norm` is 0, `silent` is true, and `vol_db`
is null because JSON cannot represent FL's negative infinity. Raw scalar API
infinities are returned as null with an explicit `nonfinite_value` label.

`live api-catalog`, `api`, `api-batch` expose the host's public scripting API
without Python eval. API return values are separate from semantic write
verification; an arbitrary raw API call is not a certified workflow.

An owned worker also supports read-only window observations without activating
the desktop or contacting a controller that may be blocked by a modal dialog:

```powershell
flstudio session windows --session private-work/session.json
flstudio session screenshot --session private-work/session.json --output main.bmp
```

For a modal or popup, pass its HWND from `session windows` as `--window`.
Capture has a three-second limit; a timeout leaves FL running. Process creation
identity and controller identity are checked, but the returned controller state
age is explicit: this is not a fresh query of project contents. The output is a
new PNG or BMP; pixel content still requires inspection. The native FL26 main window
and a separate Mixer popup have been visually checked on this machine.
`session start --desktop interactive` additionally opens a visible owned worker,
but requires all other FL instances to be closed to prevent FL forwarding the
project into an existing editor. Private mode can keep the user's editor open.

After inspecting a screenshot, submit input to its bound window:

```powershell
flstudio session screenshot --session private-work/session.json --window HWND --output menu.png --receipt menu.json
flstudio session input --session private-work/session.json --observation menu.json --key enter
```

`--move X Y`, `--click X Y`, `--drag X1 Y1 X2 Y2` use screenshot window pixels.
Input checks the owned process creation, controller identity, HWND/class and
geometry. It never moves the global pointer. FL popup menu mouse activation
was unreliable; use observed keyboard navigation there. Input returns
`unknown/input_submitted_effect_unverified`; a later getter or native artifact
must establish the intended result. Canvas fade dragging was checked against
actual saved FL26 fade values (958.333 to 1437.5 ms).

## Exact score, recording and Mixer jobs

`piano-roll queue --session ... --channel N --pattern N --job NEW.json`
binds the target through the actual Channel Rack and F7, then prepares a
uniquely named Piano Roll dispatcher. Inspect its captured menu, select that
exact script, and run `piano-roll result --job NEW.json`. Do not blindly run
the last script. A read job returns actual Score note properties. For mutation,
add `--read-job PREVIOUS.json` plus `--notes notes.json` or `--edit edit.json`.
The exact prior score must still match. Native saved notes must match the
explicit target, while other Pattern/channel scores stay unchanged. Result
collection saves an owned checkpoint. Native reopening preserves musical
properties; FL clears the transient note-selection flag.

`recording prepare --session ... --pattern N --job NEW.json` queues arming.
If FL opens first-use recording setup, inspect it and choose **Notes and
automation** using the captured owned controls. Then `recording start --job
NEW.json --request plan.json`, `status`, `cancel`, and `verify` manage the job.
Plans use `clock: "seconds"` or `"ticks"`, sorted `points` with `at`, `target`,
`value`, and `stop_at`. Target kinds: `tempo`, `channel_volume`, `channel_pan`,
`mixer_volume`, `generator_param`, `effect_param`. The native result is Pattern
event data, not a fabricated Automation Clip. Cancellation stops/disarms and
retains points already recorded. Native evidence covers ten mixed targets,
another plugin instance unchanged, actual playback and WAV. Observed callback
lateness was 0–6 ticks; native positions differed from sampled Song position
by at most one tick. This is not sample-accurate scheduling.

`mixer prepare-expand --session ... --count N --job NEW.json` saves a baseline
and opens the real Mixer menu. Inspect and activate **Insert one**; FL inserts
before the last ordinary track. Inspect the next menu and **Move right** to
restore that original track's position. `mixer verify-expand --job NEW.json
--output NEW.flp` checks count, original scalars/routes/opaque effect bytes,
channel routing and native saving. Expansion 16→17→18 was verified, including
reopening. These are explicit UI jobs, not an unattended menu-coordinate macro.

## Additional saved fields

Channel settings include delay/fat/filter/level/time/tracking/key region/cut
groups, Layer flags/children and Sampler precomputed controls. Availability is
layout-specific; raw fields do not imply Hz/ms units. Automation channels are
not treated as instrument level controls. Mixer edits additionally support
polarity, channel swap, processing flags, hardware raw selectors and 3-band EQ.
Hardware selector values do not prove physical routing on another device.

`plugin_settings` items select `channel` or `track`/`slot` and one of
`wrapper`, `native`, `notebook`. Wrapper writes accept `smart_disable` and
`threaded_processing`; VST MIDI/processing fields are read-only. Small raw
profiles cover BooBass, Fruit Kick, Plucked!, Balance, Blood Overdrive, Fast
Dist, Send, Stereo Enhancer, Soundgoodizer; Center has a format reader but
was not installed for native validation. Notebook patches use
`{"pages":[{"index":2,"text":"工程笔记 🎹"}],"active_page":2,"editable":true}`.
Other pages, unknown headers and trailers are preserved. The installed native
profiles expose all 36 EQ2, 15 Reeverb 2 and 18 Limiter controls in saved REC
units, calibrated through native load/readback. These are not arbitrary
private-preset parsers; unchanged preset-owned values remain null.

## Evidence and remaining gaps

46 installed FL factory projects retain exact no-op bytes and match flpkit's
core counts. Real reference FL20/24/25 fixtures also matched the shared core
fields; this is not native execution on those older FL versions. On this
machine, three warm runs over the factory corpus had read medians 0.360s
(CLI) / 0.385s (flpkit); an existing 1000-point curve write was effectively
equal at 13.8ms / 13.6ms. These are local measurements, not general rankings.

The live Score dispatcher, recording setup, deadline jobs and dynamic Mixer
creation above now have native evidence. A genuine mixed 80/100/120-byte
Playlist corpus has not been obtained; synthetic boundary/preservation checks
are not native certification of those historical layouts. FL26 observed clips
use 88-byte records, including GUI fades. A generic offline fade-tail writer is
not supplied and is not a capability of the cited reference reader either.
The owned canvas path was rendered both before and after the drag; both WAVs
were 4.0156 seconds and the measured RMS changed from 0.198565 to 0.197303.
Evidence is in `.lab/fullstack/gui-20261028-01/fade-audio-evidence.json`.
## Reference runtime comparison

The first same-input runtime pass is recorded in
`.lab/fullstack/reference-runtime-evidence.json`. On the FL26 `NewStuff.flp`
fixture, CLI inspection decoded 45 channels, 8 Patterns, 213 notes and 1494
Playlist items. flpdiff's JSON info path decoded 45 channels, 8 Patterns and
one arrangement but no notes. Its process median was 41 ms; the CLI's common
summary inspection fast path was 111 ms. The two timings describe different
outputs; the score and Playlist coverage must be judged separately.

For the same saved edit endpoint (32 notes, one clip move and 1000 automation
points), the warm library API medians were 9.5 ms for CLI and 26.6 ms for
flpkit, with equal independent readback. The cold API process medians were
measured separately because startup and validation are part of an Agent's cost.
ts-flp's same-process metadata read/write medians were 2.5/14.7 ms, while its
surface stops at metadata, time and sample paths. Crypto's PyFLP route and
direct PyFLP parser both failed on this FL26 fixture with the recorded
compatibility errors. FLPx and dawtool imports also retain their actual source
failures in the evidence.

The reference comparison is partial; the release claims only the verified scopes above. Live reference workflows,
their setup costs, and a genuine mixed 80/100/120-byte native Playlist corpus
still have to be compared before declaring the CLI comprehensively superior.
