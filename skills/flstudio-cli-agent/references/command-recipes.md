# Command recipes

Set the executable once:

```powershell
$fl = Join-Path $env:USERPROFILE '.local\bin\flstudio.exe'
```

## Inspect and checkpoint

```powershell
& $fl project inspect --input song.flp --summary
& $fl project snapshot --input song.flp --focus project --focus channels --budget 8000 --output state.json
& $fl project snapshot --input song.flp --focus mixer --focus playlist --budget 10000 --since state.json
& $fl project validate --input song.flp
```

## Build or edit a saved copy

```powershell
& $fl project build --request beat.json --output beat-01.flp
& $fl project edit --input beat-01.flp --request mix.json --output beat-02.flp
& $fl project diff --before beat-01.flp --after beat-02.flp
& $fl project validate --input beat-02.flp
```

## Render and inspect actual PCM

```powershell
& $fl render wav --project beat-02.flp --output beat-02.wav
& $fl audio inspect --input beat-02.wav
```

## Author or record automation

Saved-project curve editing does not need a running FL window:

```powershell
& $fl automation list --project beat-02.flp
& $fl automation edit --project beat-02.flp --channel 0 --points points.json --output beat-03.flp
& $fl automation create --project beat-03.flp --request curve.json --output beat-04.flp
```

Automation point positions are **local beats in the source clip**. At constant
tempo, a point plays at `clip.start_tick / PPQ + point.position_beats -
clip.source_window.start`; the Automation source window is reported in beats.
When moving an excerpt to beat0, preserve its original automation source window
or translate the points by the excerpt offset. Moving only its Pattern does not
move the linked curves. `playlist edit` takes `source_start_tick` in ticks, even
for an Automation Clip. Confirm the target's saved IID, active notes, clip mute,
enabled Playlist track and selected arrangement before comparing audio.

For `channel_pitch`, first use an unmistakable held-note change on the **actual
sounding channel**, then test the intended small gestures. On the calibrated
native Sampler control with `range_raw:[0,12800]`, 0.5 is neutral and0.45 is
approximately−480cents. This is a scoped calibration, not a universal plugin
parameter scale. A saved/read-back curve alone does not prove a pitch effect;
render a dry single voice and inspect an interval that actually contains it.

For real-time sampling in an owned worker:

```powershell
& $fl session start --project song.flp --output-dir work-session
& $fl recording prepare --session work-session\session.json --pattern 1 --job work-session\recording.json
& $fl recording start --job work-session\recording.json --request recording-plan.json
& $fl recording status --job work-session\recording.json
& $fl recording verify --job work-session\recording.json
& $fl session save --session work-session\session.json --output recorded.flp
```

The recording plan chooses `clock` (`seconds` or `ticks`) and a target such as
`tempo`, `channel_volume`, `channel_pan`, `mixer_volume`, `generator_param`, or
`effect_param`. A cancelled recording is partial until `verify` says otherwise.

## Discover and apply plugin or mixer state

```powershell
& $fl plugin presets --plugin Sytrus --search bass
& $fl sytrus params --project beat-02.flp --channel 0
& $fl plugin params --project beat-02.flp --track 0 --slot 9
```

Use `docs/sytrus-mixing.md` for request shapes. Preserve unknown plugin bytes and
use an explicit new output path.

## Owned live worker

```powershell
& $fl session start --project song.flp --output-dir work-session
$session = 'work-session\session.json'
& $fl live --session $session status
& $fl live --session $session query --command cli_capabilities
& $fl session save --session $session --output live-checkpoint.flp
& $fl session stop --session $session
```

Use `session screenshot` followed by `session input` only for a worker started by
the CLI. Re-read or save after input; never infer a successful FL operation from a
submitted key or click.
