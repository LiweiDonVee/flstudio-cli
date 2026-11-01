# Plugin support and evidence layers

Measured locally on FL Studio Producer **26.1.6.5639**, Windows x64,
2026-11-02. A plugin being discovered does not imply complete control.

CLI1.2 additions have native-save/cold-reopen/audio evidence in
[Producer1.2](../producer-1.2.md): Sytrus OP鈫抐ilter/FX/OUT/PAN and four-point CUT
envelope; 3xOsc synthesis/VOL envelope; Maximus four band curves; WaveShaper
curve/drive; Delay3 controls/time; Edison/Slicex embedded PCM/cues; Slide/mono-glide.
The linked table gives exact per-plugin limits and measured observations.

| Layer / plugin | Observation | Reliable edits actually exercised | Sound and restoration | Boundaries |
|---|---|---|---|---|
| Sytrus Default family | Full opaque state plus validated native-field inspection; host parameter catalog is separate | Six-operator FM/RM routes and direct OUT, ratio, SH, first 32 harmonic coefficients, enabled four-point VOL envelope; selected unison/level host overrides | Matrix direction, frequency, harmonic amplitudes and envelope changes calibrated with native WAV; bass/lead/pad candidates saved, cold-reopened and rendered | Only two anchored Default layouts: factory V2 and FL26-native V3. Arbitrary factory/user layouts rejected; not a general Sytrus decoder |
| Sytrus unsupported state | Plugin identity, opaque full-state preservation and host discovery | Existing host-exposed controls or native UI/capture | A candidate still requires actual save/reopen and audio checks | Arbitrary envelope topology, filter types/Send-to-next, custom phases, full modulation/arp/internal resource editing are outside the deep adapter |
| Surge XT VST3 1.4 local build | 918 named parameters observed; physical display values read separately | Selected Classic/Sine oscillator type/shape, FM/RM mode, mixer/mute, unison, amp envelopes, filters, routing, VCA/global level | Three roles; independent pad exploration and continuation; requested values checked after cold reload, full state retained, actual WAV repeated | This is a tested subset, not 918 verified writable controls. Enums quantize; changing oscillator type can reset dependent controls. Generic API does not reveal all modulation routes/assets |
| 3x Osc | Typed factory/native state, host catalog separate | Wave/tuning/mix and native VOL envelope; see Producer1.2 for per-layout fields | Real sine/detuned/pluck and Slide/glide states saved/cold reopened/rendered | Default-derived layouts; sample waveform and arbitrary hidden host state not covered |
| Fruity Reeverb 2 | Existing saved parameter profile and complete slot state | Low-wet lead insert and decay; complete FX transfer/undo | Native lead audio and saved/reopened slot state exercised | Existing profile scope only; not a claim for arbitrary native effects |
| Other installed generators/effects | Preset/module identity and host discovery when the host exposes them | Normalized host writes with independent addressed readback | Per-candidate native checkpoint and cold-reopen/audio evidence required | Hidden controls need a scoped adapter or native UI; unsupported writes remain unresolved |

The Sytrus adapter checks prefix, repeated operator anchors, envelope layout and
field ranges before editing; size alone is insufficient. Native import upgrades
the factory envelope container. Semantic requested fields are checked across
that upgrade; the complete native sound state is then compared across a second
load. Raw envelope time is **not** advertised as seconds.

Complete state means native FLP channel/plugin/host envelopes and the selected
dedicated insert FX, not exhaustive knowledge of every opaque field. Known
channel samples are bundled with tasks; plugin binaries/licenses and hidden
sample/wavetable/IR references remain external dependencies. No third-party
plugin is purchased, relicensed or uploaded by this workflow.

Surge's installed file reports 1.4.0; source identity is local official nightly
`dab78c6170732b3883216e569a84bf084ae0ea97`. The official 1.3 manual informs design
but does not establish the exact parameter layout of that nightly.

Read [validation](validation.md) for execution versus listening evidence, and
[Sytrus implementation details](sytrus.md) for supported raw fields.


New development additionally verifies KEY/velocity/Mod X/Y two-point operator
VOL and filter CUT maps, with separate MIDI-source native renders and an
8-map full-state cold reopen. See [Sytrus expression](../sytrus-expression.md).
This does not imply arbitrary modulation or graph topology. Addressed native
[previews and listening](../audio-preview.md) preserve known Mixer-sidechain
controls, support all five listening scopes, and expose explicit audio receipts.
The optional DSH listener has actual native-model WAV/MP3 evidence; it is
separate from the current DSH conversation transport.
