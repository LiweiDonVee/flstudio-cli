# FL Studio CLI 1.2.0 — Producer plugins, Slide and audio diagnostics

This release expands real plugin sound design while retaining the isolated
candidate → native save → close → cold reopen → render workflow. It adds
question-led signal experiments for Agents that cannot listen.

## What changed

- **Sytrus remains the primary adapter:** OP-to-filter and OP/filter-to-FX/OUT
  routing, source PAN and enabled four-point filter CUT envelopes complement
  the existing FM/RM, ratio, shape, harmonics and volume envelope operations.
- **Scoped Producer plugin designs:** 3xOsc wave/tuning/mix/volume envelopes;
  Maximus Low/Mid/High/Master transfer curves; WaveShaper curve/drive;
  Delay3 controls and tempo-synced time; Edison/Slicex embedded PCM/cue import,
  editing and export. Effect-host writes have independent cold-readback checks.
- **Native articulation:** named `slide`, `porta`, `muted`, `color`, readable
  `notes articulation`, and verified native Slide/Mono glide in Sytrus/3xOsc.
- **`audio analyze`:** overview, pitch, envelope, harmonics and delay purposes,
  explicit ambiguity/nulls and next experiments. An actual WaveShaper example
  that only changed gain was detected and retained as a failed hypothesis.
- **Runtime fixes:** owned-project saving focuses FL's host window so Slicex
  cannot intercept Save as a sample export; Sampler targets can participate in
  sound-design tasks without falsely requiring a generator parameter catalog.

## Download and audition

- **`flstudio_cli-1.2.0-py3-none-any.whl`**: installable CLI. For analysis,
  `uv tool install "flstudio_cli-1.2.0-py3-none-any.whl[sound-design]" --python 3.12`.
- **`flstudio-producer-1.2.0.zip`**: 32 real native cases, 64 saved/cold-reopened
  FLPs, raw solo/context/accompaniment/repeat/reopened audio, within-group
  constant-gain RMS-matched previews, requests, analysis and verification records.
  Extract and read its README; after moving the folder run `restore_samples.py`
  using the installed CLI's Python to write new locally rebound FLP copies.
- **`flstudio-agent-skills-1.2.0.zip`**: the main FL Agent and sound-design
  specialist Skills, with progressive plugin and signal-experiment references.
- **Five standalone WAV previews:** Sytrus FM/filter context, 3xOsc pluck
  context, saturation/echo context, Slicex regions solo and Sytrus Slide solo.
  These are original native render levels; the full bundle preserves both raw
  audio and level-matched comparisons. Previews are mechanism demonstrations.
- **`SUPPORT-1.2.0.md`**, **`AUDIO-ANALYSIS-1.2.0.md`** and **`SHA256SUMS.txt`**:
  scope, analytical methods and downloadable-file integrity.

No FL Studio/plugin binary, factory FST, private song or license is bundled.
The authored context and calibration inputs are included for reproducibility.

## Verification and support boundaries

Verified on **Windows x64, Python 3.12, FL Studio Producer26.1.6.5639**.
Nine concise invariant tests passed. All 32 selected cases completed native
save/cold-reopen/audio checks. The installed entrypoint independently refined
WaveShaper/Delay3 and repeated that loop. A moved Slicex case was rebound and
cold-rendered to **sample-identical PCM**. Skill/delegation admission was checked
in the actual local DSH runtime; the local preset is2.4.0.

These are **bounded operations, not whole-plugin coverage**. Sytrus arbitrary
preset layouts, filter-type/Send-to-next and arbitrary envelope topology;
Maximus spare/A-B bank switching; arbitrary Slicex articulator/trigger maps;
and all Edison DSP remain outside this adapter scope. CLI PCM processing is
separate from native Edison processing; native Normalize alone was separately
observed and restored. Mono overlaps glide independently of a per-note marker;
the marked-porta examples do not isolate that marker's necessity.

Signal features are not listening or musical-quality scores. **No subjective
listening acceptance was performed for these new cases.** Pitch assumes one
voice, harmonic fitting a stationary dry comparison, delay an isolated pulse.
RMS matching is not LUFS/perceived-loudness matching; true peak is not claimed.

Read the [full support matrix](https://github.com/LiweiDonVee/flstudio-cli/blob/v1.2.0/docs/producer-1.2.md),
[signal methods](https://github.com/LiweiDonVee/flstudio-cli/blob/v1.2.0/docs/audio-analysis.md)
and [main-agent delegation workflow](https://github.com/LiweiDonVee/flstudio-cli/blob/v1.2.0/docs/sound-design/README.md).
