# Signal experiments when you cannot listen

Use the existing audition WAVs before rendering more. `audio inspect` gives
levels/timing; audition gives envelope/stereo/context occupancy and repeat/cold
comparison. `sound-design compare` makes constant-gain RMS-matched previews and
preserves raw audio. Add only the experiment that resolves the next decision.

```powershell
& $fl audio analyze --input solo.wav --purpose overview --output overview.json
& $fl audio analyze --input solo.wav --purpose pitch --request pitch.json --detail --output pitch-result.json
& $fl audio analyze --input after.wav --reference before.wav --purpose harmonics --request harmonics.json --output harmonic-result.json
```

| Need | Request / experiment | Interpretation |
|---|---|---|
| Actual Slide/glide | pitch `{"monophonic":true,"min_hz":40,"max_hz":400}` on one dry voice | Look for intermediate pitches. Verify notes really imply one voice; octave layers can share a strong period. Confidence is periodicity, not probability. |
| Attack/tail fits rhythm | envelope `{"note_on_seconds":0,"note_off_seconds":0.5,"next_on_seconds":0.75,"end_seconds":0.75,"frame_ms":5}` | Use **actual** note timings, not these example numbers. Relative−40dB tail occupancy and pre-next energy test timing, not taste. Truncation means extend/choose another window. |
| Distortion versus gain | harmonics `{"start_seconds":0.1,"end_seconds":0.4,"fundamental_hz":65.406,"harmonics":8}` plus aligned dry WAV | Best-fit gain can explain the whole change. Gain-compensated residual plus Hn/H1 tests a stationary single-note hypothesis. First compare unchanged repeats: phase/randomness can also cause residual. |
| Rhythmic echo/stereo bounce | delay `{"expected_delay_seconds":0.375}` plus dry isolated pulse | Short note then silence. Compare detected spacing with BPM-derived expectation and channel RMS per echo. Dense material cannot uniquely identify the delay. |
| Register/space conflict | existing audition solo+context+accompaniment and occupancy | Locate simultaneous band/rhythm/register use, inspect note lengths/foreground role; occupancy alone is not auditory masking. |

Tick→seconds at constant tempo is `tick/PPQ*60/BPM`; note-off is start+length.
Use project tempo-map timing for automation. Sytrus raw envelope time and
channel slide_raw are not universal seconds mappings. Pitch uses100ms frames
by default, therefore ±50ms integration, even with10ms hop. Enlarge windows for
very low notes. Frequency estimates come per channel, avoiding mono cancellation.

Read `usability` first: `usable`, `ambiguous`, `unavailable`. Unknown frames stay
null; never impute them, count zero crossings as pitch on complex voices, or call
a strong periodicity score proof of monophony. Follow `next_experiment` when
provided. Use `--output` to keep details outside chat; read only a small interval.
Harmonic fits require at most five stationary seconds. All tools use NumPy,
not audio models; no extra model installation is necessary.

Keep a short ledger: role/listening phrase → mechanism → bounded edit →
observation under fixed conditions → remaining ambiguity → next decision.
For "warm", separate less bright/soft transient/low-mid weight/saturation.
For "ethereal", separate slow attack/modulation/inharmonicity/stereo/long space.
For "tight", inspect rhythm/release before EQ. Preserve alternative aesthetics;
do not optimize every candidate toward one metric target.

Real diagnostic examples: an initial WaveShaper branch was only+12.34dB gain
(residual−74.19dB, H3/H1 unchanged); a reachable knee produced residual−7.78dB
and altered harmonic ratios. Delay3 measured374.15ms against375ms expected.
Slide produced continuous F0 in Sytrus and3xOsc; different-color Slide left the
source pitch unchanged. These are mechanism observations, not listening scores.

Without hearing, retain `listening.status:not_performed` and call recommendations
provisional. Deliver raw and matched context/solo WAVs for a listener. Metrics
can falsify a mechanism claim and find conflicts; they cannot establish
"sounds natural", artistic quality, or the best aesthetic choice.
