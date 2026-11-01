# Producer-scoped operations (CLI1.2)

Use `sound-design support --project FILE --channel N` for the actual state and
its insert adapters. `plugin design-inspect --project FILE --channel N` or
`--track T --slot S` returns typed saved fields. `design-edit --request JSON
--output NEW.flp` is file readback only; use candidate/audition for native
save→close→cold reopen→audio. All following are bounded Default-family support,
not entire-plugin control. Dedicated insert required for effect editing.

## 3xOsc

Candidate `generator_design` example:

```json
{"oscillators":[{"oscillator":1,"waveform":"saw","fine_cents":-5},{"oscillator":2,"waveform":"saw","coarse_semitones":0,"fine_cents":5}],"mix2_raw":64,"mix3_raw":0}
```

Waveforms: sine/triangle/square/saw/rounded_saw/noise; sample mode requires
separate resource verification and is rejected. Coarse±24semitones/fine±100cents.
Mix0..128 controls relative ratios, not independent linear gains. Factory state
needs one native save before pan/phase/detune or the following VOL envelope:

```json
{"volume_envelope":{"enabled":true,"predelay_raw":100,"attack_raw":100,"hold_raw":100,"decay_raw":10000,"sustain_raw":0,"release_raw":100}}
```

Times are native100..65536, not milliseconds; sustain0..128. Real native sine,
detuned pair and pluck cases survived full save/cold/audio. Per-oscillator phase
and random-phase changes may need repeated renders rather than sample equality.

## Maximus / WaveShaper / Delay3

Candidate `effect_designs:[{"slot":0,"design":...}]`:

- Maximus: `{"bands":{"low":{"points":[{"x":0,"y":0},{"x":0.5,"y":0.32},{"x":1,"y":0.5}]}}}`.
  Bands low/mid/high/master; first/default bank edited, spare retained. Graph
  coordinates are normalized native log-level positions, not physical dB.
  Other controls use `effect_host_params:[{"slot":0,"param":47,"value":0.6}]`
  after actual discovery (47 was tested Master pre-gain on FL26). Do not infer
  all bands' host indices or raw ranges from that one example.
- WaveShaper: `{"points":[{"x":0,"y":0},{"x":0.015,"y":0.03},{"x":0.04,"y":0.05},{"x":0.1,"y":0.06},{"x":1,"y":0.08}],"pre_raw":256}`.
  Curves2..64points, x strictly0→1, y0..1, optional tension−1..1. Existing
  polarity mode retained. Pre0..256, mix/post0..128. Test gain-compensated dry
  residual: a knee above all actual input peaks may be only a gain change.
- Delay3: `{"time_steps":3,"controls_raw":{"model":2,"offset":4500,"feedback":1800,"output_wet":2800,"output_dry":6000}}`.
  One step=sixteenth;3steps=375ms at120BPM, measured374.15ms on an isolated pulse.
  Raw control names are discoverable in design-inspect; raw values are not
  inferred Hz/ms/%. Test delay tails in actual rests and mono. Keep feedback
  below self-oscillation when measuring individual echoes.

## Edison and Slicex

Design object: `{"audio_file":"ABSOLUTE/input.wav","trim_frames":[0,88200],"normalize_peak_dbfs":-6,"regions":[{"name":"Body","start_frame":0,"end_frame":30000,"key":60}]}`.
Edison is an effect design; Slicex a generator design. Deck defaults a, Slicex b
is also addressable. PCM16/24/32 or float32 WAV, at most120seconds per asset.
Optional gain_db/normalization/trim are **CLI PCM operations**, not Edison DSP.
The actual sample is embedded and exact decoded PCM+regions checked across
native/cold saves. Keep the original recording and avoid normalizing candidates
before nonlinear processing just to make comparisons louder.

Regions follow ordered Default import keys60,61,... (max72). Inspector field
`expected_import_key` is a convention, **not an observed arbitrary custom map**.
Custom key maps/articulators and arbitrary Slicex stretch behavior remain
outside the adapter; verify the rendered phrase. Real60/61/62 triggered distinct
65.4/130.8/98Hz source regions. `plugin sample-export ... --deck a --output NEW.wav`
exports exact embedded native WAV+cue metadata. Native Edison Normalize was
separately observed and restored; do not extend that evidence to all native tools.

## Native Slide and channel glide

Named note fields `slide`, `porta`, `muted`, `color` are accepted by notes
replace/build/transform; raw fields remain compatible. Read via
`notes articulation --project FILE --pattern 1 --channel 0`.

AtPPQ96/120BPM, sustain normal key36 ticks0..288; add same-color
`{"key":48,"start_tick":96,"length_tick":96,"velocity":100,"slide":true,"color":0}`.
The Slide's length specifies its transition; it targets the already sounding
same-color voice. Different-color negative control stays at the original pitch.
Actual Sytrus and3xOsc audio confirm intermediate pitches.

For overlapping **ordinary** notes, channel settings
`{"polyphony":{"mono":true,"porta":true,"slide_raw":1660}}` make a slow native
glide. Range0..1660 is nonlinear, not ms. `mono:true` itself glides overlaps;
per-note `porta:true` is a separate persistent marker, whose independent effect
was not isolated by the mono examples. Sytrus's own `portamento` control is also
separate. Native note Slide is not generic VST pitch-bend. Verify F0 on dry solo
with [analysis.md](analysis.md), preserve colors and actual musical articulation.
