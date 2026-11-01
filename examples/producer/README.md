# Producer1.2 examples

Candidate request files go to `sound-design candidate --task TASK --request FILE`.
They are modifications of a task's actual target, not project-build requests.
Replace `ABSOLUTE` asset paths; find installed Default FSTs with `plugin presets`.
No Image-Line binaries or factory presets are bundled. Parent ids refer to
previous ready branches; create the baseline first or remove/adapt the parent
only when the target is already the intended native state.

- `sytrus-filter-motion.json`: native-saved harmonic carrier→F1/CUT motion.
- `threeosc-single.json`→`threeosc-detuned.json`→`threeosc-pluck.json`:
  separate baseline, synthesis mechanism and envelope refinement.
- `maximus-low.json`, `waveshaper-saturation.json`, `delay3.json`: effect-chain
  requests, dedicated insert required. Per-layout scope is in
  [Producer1.2](../../docs/producer-1.2.md).
- `slicex-regions.json`: region sample source is a two-second authored render;
  region positions must be adapted to any other source. Key60..62 expected
  ordered mapping still requires an actual rendered trigger phrase.
- `slide-notes.json`: a notes array for `notes replace --notes FILE`; fixed
  example assumesPPQ96. Different colors intentionally do not bend the base.
- `portamento-candidate.json`: requires overlapping ordinary notes. Raw1660
  is nonlinear native time, not milliseconds; Mono itself glides overlaps.
- `analyze-*.json`: analysis requests, not candidate requests. Use actual note
  timing/F0/BPM. Envelope numbers are for the110BPM/PPQ96 example phrase;
  delay375ms for120BPM. See [methods](../../docs/audio-analysis.md).

```powershell
& $fl sound-design candidate --task work/task.json --request examples/producer/threeosc-single.json
& $fl sound-design audition --task work/task.json --candidate single-sine
& $fl audio analyze --input work/candidates/single-sine/audio/solo.wav --purpose envelope --request examples/producer/analyze-envelope.json --output envelope.json
```

The local case bundle contains independently cold-reopened FLPs, original
solo/context WAVs, complete evidence and a portable sample rebinding script.
The JSON files here are small reproducible operation examples, not assertions
that arbitrary music or plugin layouts accept the same values.
