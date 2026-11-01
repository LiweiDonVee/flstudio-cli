# Validated Sytrus design adapter

Use `sytrus design-inspect --project FILE --channel N` before editing an existing
state. `sound-design support` declares the exact current scope. Deep edits admit
the installed Default family and its FL26.1.6 native saves; other layouts are
rejected. `init:true` loads the locally installed Default container and clears
the old generator host overrides. No Image-Line preset is bundled with the CLI.

Candidate example:

```json
{
  "id":"fm-body",
  "description":"Carrier body with a decaying FM attack",
  "mechanisms":["directed two-operator FM","independent modulator envelope"],
  "sytrus_design":{
    "init":true,
    "matrix":[{"mode":"fm","source":2,"target":1,"value_raw":60}],
    "operators":[
      {"operator":1,"ratio":2,"volume_envelope":{"enabled":true,"attack_time_raw":0.01,"decay_time_raw":0.3,"sustain":0.7,"release_time_raw":0.1}},
      {"operator":2,"ratio":4,"volume_envelope":{"enabled":true,"attack_time_raw":0.005,"decay_time_raw":0.12,"sustain":0.08,"release_time_raw":0.05}}
    ]
  }
}
```

- `source:2,target:1` means OP2 modulates OP1. Equivalently row1/column2.
  `mode` is `fm` or `rm`; both matrices coexist. Raw depth is -256..256.
  `source:1,target:"out"` sets direct OP1 output. For shared filter/FX/OUT use
  `routes`; for source PAN use `pan`, as below. Filter-to-filter Send to Next is
  separate and not implemented as an arbitrary matrix edge.
- `ratio` is 0..64 with four decimal places. On the tested host, Note.key36
  ratio1/2 produced 65.441/130.882Hz. Fix the actual notes and check the output;
  do not assume another DAW's octave labels.
- `shape_raw` is SH 0..512; its effect depends on the existing harmonic shape
  and other modifiers. `harmonics` is an array such as
  `[{"harmonic":2,"coefficient_raw":0.25}]`, first32 only. Coefficients are
  linear amplitudes; GUI pillar heights are logarithmic.
- `volume_envelope` edits the existing four points. `enabled` defaults true
  when this section is present because factory Default has it disabled.
  `attack_time_raw`, `decay_time_raw`, `release_time_raw` are serialized segment
  durations, not a claimed universal seconds mapping. Sustain/levels are 0..1.
  The adapter preserves existing curve/sustain/loop metadata.
  Local held-note calibration at 120BPM gives useful starting anchors:
  release raw .12 reached the -40dB-relative frame threshold about 46ms after
  note-off; raw .8 about 360ms. Curves, time modifiers and the measurement
  threshold matter. These are measured starting conditions, not a universal
  conversion formula; reuse the saved calibration before writing another probe.
- Existing integer host controls (unison, master level, filter offsets etc.)
  use a separate `sytrus` array. The CLI applies deep initialization first and
  host overrides afterwards. Hidden state is captured in the complete FLP.

Do not use a Sytrus preset from another family as if these offsets apply to it.
For unsupported layouts, either intentionally reinitialize a new candidate or
use an owned native UI edit plus `sound-design capture`. Save/reopen/audition
still apply; a successful raw-state edit alone is not the audio proof.

Sources and design hypotheses are searchable with `sound-design knowledge`.
The full maintained adapter evidence is `docs/sound-design/sytrus.md` in the
CLI repository; measured cases are under `.lab/sound-design/sytrus-adapter`.

## Routed filter movement (1.2)

This is a modification of a Default-derived carrier candidate, not a standalone
init that sets every synthesis field. Host filter cutoff/envelope amount and
chorus controls are separate from the native envelope/routing structure:

```json
{
  "id":"filter-motion","parent":"carrier",
  "description":"Carrier through a moving low-pass body",
  "mechanisms":["OP1 to Filter1","independent cutoff envelope"],
  "sytrus_design":{
    "routes":[
      {"source":1,"target":"out","value_raw":0},
      {"source":1,"target":"filter1","value_raw":256},
      {"source":"filter1","target":"out","value_raw":256}
    ],
    "filters":[{"filter":1,"cutoff_envelope":{"enabled":true,"attack_time_raw":0.004,"peak_level_raw":1,"decay_time_raw":0.18,"sustain_level_raw":0.15,"release_time_raw":0.08}}]
  },
  "sytrus":[{"param":"filter1.cutoff","value_raw":60},{"param":"filter1.cutoff_envelope","value_raw":230}]
}
```

Operator source numbers1..6 and string sources `filter1|filter2|filter3` are
explicit. Valid destinations depend on source: operators may send to filters;
operators/filters may send to `fx|out`. Values−256..256. PAN is
`"pan":[{"source":"filter1","value_raw":-192}]`. To use internal chorus,
route Filter1 out0/fx256, then set existing `chorus.order/volume/depth/spread`
host controls. These branches were saved/cold-reopened/rendered in real FL.
Envelope levels0..1 are normalized articulator coordinates, not cutoff Hz;
native scales controlled by the host envelope-amount knob are reported separately.
Arbitrary filter type, free-point envelopes and all internal effects are not
claimed. Compare actual fixed context and check mono before choosing a wider FX.
