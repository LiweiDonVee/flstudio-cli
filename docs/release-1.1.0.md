# FL Studio CLI 1.1.0 — delegated plugin sound design

An Agent can delegate a musical role in an actual arrangement, receive distinct
editable sounds with solo/context audio, apply a choice, undo it, and send it
back for revision. Sytrus is the primary deep adapter.

## What changed

- `sound-design prepare/candidate/audition/compare/report/apply` covers isolated
  branches, complete native state, cold reopen, repeated rendering, compact
  handoffs, and application/undo by channel IID. Interrupted work can resume.
- Sytrus synthesis from supported initialization states includes six-operator
  FM/RM/OUT, ratios, SH, 32 harmonics and enabled four-point volume envelopes.
  `design-inspect --summary --operator N` expands only the needed detail.
- Generic host operations were separately exercised with Surge XT. Requested
  values are checked after reload; unsupported or quantized values stay explicit.
- The specialist Skill includes six executable design recipes and 14 attributed
  original sources. DSH preset 2.3.0 adds
  `design_sound → fl-studio-sound-designer`, follow-up and compact reporting.

## Listen and recover

[Download the complete examples and recoverable projects](https://github.com/LiweiDonVee/flstudio-cli/releases/download/v1.1.0/flstudio-sound-design-1.1.0.zip).
The archive contains 18 curated role/reference/revision cases, three additional
real DSH delegation cases, editable FLPs, before/cold-reopened states, bundled
drum samples, raw and level-matched WAVs, operation records, the Skill and evidence.
It contains newly authored music, not private user projects.

| Example | Solo | Same actual arrangement |
|---|---|---|
| Sytrus FM transient bass | [WAV](https://github.com/LiweiDonVee/flstudio-cli/releases/download/v1.1.0/demo-bass-sytrus-fm-solo.wav) | [WAV](https://github.com/LiweiDonVee/flstudio-cli/releases/download/v1.1.0/demo-bass-sytrus-fm-context.wav) |
| Sytrus additive lead | [WAV](https://github.com/LiweiDonVee/flstudio-cli/releases/download/v1.1.0/demo-lead-sytrus-additive-solo.wav) | [WAV](https://github.com/LiweiDonVee/flstudio-cli/releases/download/v1.1.0/demo-lead-sytrus-additive-context.wav) |
| Surge specialist pad | [WAV](https://github.com/LiweiDonVee/flstudio-cli/releases/download/v1.1.0/demo-pad-surge-specialist-solo.wav) | [WAV](https://github.com/LiweiDonVee/flstudio-cli/releases/download/v1.1.0/demo-pad-surge-specialist-context.wav) |

[Actual DSH main-Agent applied result](https://github.com/LiweiDonVee/flstudio-cli/releases/download/v1.1.0/demo-dsh-applied-context.wav).
These individual downloads are raw renders; matched comparison sets are in the
archive. These are execution examples, not a subjective ranking.

After extracting elsewhere, follow the included `RECOVERY-1.1.0.md` to rebind
the three drum sample paths into a new FLP copy. `selected.flp`, `undone.flp`
and `continued.flp` demonstrate selection, restoration and a later release edit.
Full native state is preserved; restoration does not require parameter replay.
FL Studio, plugin binaries and licenses are external requirements.

## Support scope

Measured on Windows x64, FL Studio Producer **26.1.6.5639**:

| Component | Verified in this release | Boundary |
|---|---|---|
| Sytrus | Native parameter changes, signal changes, complete save/cold-reopen/render; FM/RM/additive/envelope directions across bass/lead/pad | Deep editing only for two anchored Default-family layouts. Arbitrary presets, filter/FX matrices, custom phases and arbitrary envelope topology are outside this adapter |
| Surge XT VST3 | Selected oscillator, FM/RM, unison, filter, amp-envelope and level controls; native state restoration | Tested local official 1.4 nightly `dab78c6`; 918 observed names do not mean 918 verified controls. Hidden modulation/resources are not fully exposed |
| Fruity Reeverb 2 | Lead insert, saved slot state and complete FX transfer/undo | Existing scoped parameter profile; not all native effects |
| Other plugins | Identity/opaque-state preservation and host discovery when exposed | Each plugin/control still needs write/readback/audio/restoration evidence; arbitrary-plugin coverage is not promised |

[Full support matrix](https://github.com/LiweiDonVee/flstudio-cli/blob/v1.1.0/docs/sound-design/support-matrix.md)
and [validation record](https://github.com/LiweiDonVee/flstudio-cli/blob/v1.1.0/docs/sound-design/validation.md).
Known channel samples are bundled; hidden plugin samples, wavetables and IRs
cannot be exhaustively discovered. Surge must be installed and resolvable locally.

## Evidence and limits

Nine final designed candidates and three unchanged controls passed native
state/audio checks. A separate specialist delivered three pad directions and
continued a selected result. A real DSH model session delegated, applied and
rendered its result, then recovered its final handoff in the same persisted
session after an upstream error. Wrong parameters, unsupported layouts,
quantization, render timeout, interruption and context pollution were exercised.
The focused regression suite has **7 passing tests**.

No subjective listening evaluation was performed. Signal measurements and
PCM-RMS-matched previews establish technical behavior, not musical preference,
perceived-loudness equality or superiority to a musician's preset selection.

## Install

Python 3.12+, Windows and a local licensed FL Studio installation are required
for native operations. Install the sound-analysis extra from the tagged source:

```powershell
git clone --branch v1.1.0 --depth 1 https://github.com/LiweiDonVee/flstudio-cli.git
cd flstudio-cli
uv tool install ".[sound-design]"
flstudio --version
```

A wheel and DSH preset archive are attached separately. MIDI remains optional;
sound-design tasks use private FL workers. See the
[Agent workflow](https://github.com/LiweiDonVee/flstudio-cli/blob/v1.1.0/docs/sound-design/README.md)
and [specialist Skill](https://github.com/LiweiDonVee/flstudio-cli/blob/v1.1.0/skills/flstudio-sound-design/SKILL.md).
