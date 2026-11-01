# Signal tools for an Agent without hearing

`audio inspect` already reports decoded levels/duration. `sound-design audition`
already renders solo, actual context, accompaniment, repeat and cold-reopened
context; it reports spectral/envelope/stereo/context occupancy and repeat error.
`sound-design compare` creates constant-gain RMS-matched previews, retaining raw
WAVs. Version 1.2 adds **question-led** `audio analyze` for missing diagnostics.
It uses the existing NumPy extra, no model download or new dependency.

```powershell
$fl = Join-Path $env:USERPROFILE '.local\bin\flstudio.exe'
& $fl audio analyze --input solo.wav --purpose overview --output overview.json
& $fl audio analyze --input solo.wav --purpose pitch --request pitch.json --detail --output pitch-result.json
& $fl audio analyze --input after.wav --reference before.wav --purpose harmonics --request harmonics.json --output harmonic-result.json
```

`--output` keeps the response small and writes observations separately. Read
only the relevant channel/time window. With no output file, bounded observations
are returned directly. Float32 Edison exports and PCM16/24/32 are supported;
the basic `audio inspect` integer path remains dependency-free. Optional NumPy
is needed for float32 and the analytical tools.

## Choose an experiment before a metric

| Question | Purpose / request | Interpretation and next step |
|---|---|---|
| Did routing mute/overload/widen the sound? | `overview`; optional `start_seconds`, `end_seconds` | Peak/RMS/crest, band fractions, stereo correlation, side/mid and mono RMS. Full-scale samples alone do not prove clipping. |
| Is this a step or an actual glide? | `pitch`: `{"monophonic":true,"min_hz":40,"max_hz":400}` | Independent-channel FFT normalized-square-difference periodicity, parabolic lag interpolation. Observe intermediate Hz, not only endpoints. |
| Is the sound finished before the next note? | `envelope`: actual `note_on_seconds`, `note_off_seconds`, `next_on_seconds`; optional `frame_ms` | Frame-smoothed attack 10–90%, release occupancy above a relative threshold, pre-next-note energy, truncation flag. Inspect dry voice before attributing reverb tails to an amp envelope. |
| Did distortion change anything besides gain? | `harmonics`: aligned before/dry reference, stationary single note; `{"start_seconds":0.1,"end_seconds":0.4,"fundamental_hz":65.406,"harmonics":8}` | Per-channel best-fit gain/residual and Hn/H1. Check unchanged-repeat residual first; phase, latency, modulation and randomness also make residual. |
| Does the echo match the rhythmic grid? | `delay`: one short input pulse followed by silence; dry reference; `{"expected_delay_seconds":0.375}` | Thresholded echo onsets, median spacing and per-echo L/R RMS. Dense music or self-oscillation cannot identify one unique delay. |
| Is it fighting the arrangement? | `sound-design audition` context occupancy + actual fixed context WAV | Concurrent band occupancy indicates where to investigate. It does not measure psychoacoustic masking or artistic fit. Check register, note lengths, rhythm and foreground role. |

Examples: [analysis request files](../examples/producer/). All measurement
windows must lie inside the WAV and span at most 120 seconds. Harmonic fitting
uses at most five stationary seconds. Pitch defaults to 100ms frames/10ms hop;
the frame must contain at least three periods at `min_hz`. A 10ms hop does not
make onset timing accurate to 10ms: each estimate integrates ±half the window.
Use `--detail --output FILE` for full frames; the inline summary has at most32.

## Read uncertainty as data

`usability` is `usable`, `ambiguous` or `unavailable`, with `reason_code` and an
actionable `next_experiment` where appropriate. Ambiguous/unavailable CLI results
have `status:unknown`; they are not a successful pitch or release measurement.

Pitch `confidence` is **periodicity, not probability of correct F0**. Null frames
are kept for silence, low periodicity, out-of-range and competing harmonic
periods. The tool does not fill gaps or silently correct octaves. Confirm one
voice from the project and render a solo interval before declaring
`monophonic:true`. Two overlapping octave voices can share a very strong
period. Zero-crossing counts are particularly misleading on rich/multiple voices.
Stereo channels are analyzed independently so phase cancellation in a mono sum
does not fabricate silence.

For envelope analysis, convert ticks using actual PPQ and the tempo map. At
constant tempo: `seconds = tick / PPQ * 60 / BPM`. Note-off is start+length,
not the next note start. Time-varying tempo needs the existing project timing
model. Never label an RMS window around the middle of a held note as release.

## Use features to decide the next operation

Keep an experiment ledger with: listening words/role, mechanism, changed control,
fixed conditions, observation, remaining ambiguity and next decision. Start
with the unchanged baseline. Change one mechanism or a small coherent group,
then compare the actual excerpt. Explore substantially different hypotheses
before refining a promising branch. Do not optimize all features toward a
universal target or reduce every sound to less high-frequency content.

For "warm": separate less bright, soft transient, low-mid weight and saturation
hypotheses. Use Hn/H1 or band/envelope observations to test the mechanism, then
compare loudness-matched context previews. For "ethereal": decide whether the
request means slow attack, inharmonic motion, stereo decorrelation or a long
space; stereo correlation alone cannot choose among them. For "tight": check
note rhythm and tail occupancy before adding EQ. If the issue is voicing or
arrangement, return that diagnosis rather than altering protected parts.

## Real FL evidence (2026-11-01)

- Sytrus Slide: about65.4Hz →75.5→92.7→113.9→130.8. Different-color Slide
  control stays near65.4Hz. Mono-portamento raw1660 also yields continuous
  intermediate pitches; 3xOsc verifies a separate engine, with a different octave.
- Initial WaveShaper curve: +12.34dB best-fit gain, residual−74.19dB relative,
  almost identical H3/H1. It was only gain in that input range. Revised curve
  with a reachable knee: residual−7.78dB and changed relative harmonics.
- Delay3 three steps at120BPM: expected375ms, observed374.15ms using4.99ms
  RMS frames; alternating channel dominance is observed in the repeats.
- Maximus mid-only edit: 800Hz controlled-tone band−4.10dB, 65Hz−0.04dB;
  high-only: 6000Hz−3.87dB, 800Hz−0.02dB. This tests band addressing, not taste.
- 3xOsc pluck: no energy above the relative−40dB threshold after the actual
  note-off; unchanged sine's short release occupied about15ms in this fixture.

All are real FL renders with saved/cold-reopened states. These prove specific
mechanisms and diagnostics, **not** an improvement in musical preference.
No human or audio-capable-model listening was performed in this expansion.
Return `listening.status:not_performed`; a recommendation remains provisional.
