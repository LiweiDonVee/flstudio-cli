# Producer plugins and articulation, 1.2.0

Tested in local FL Studio Producer26.1.6.5639. Native save, process closure,
separate cold reopening, requested semantic checks and raw audio renders are
distinct acceptance steps. The new adapters preserve unknown private bytes;
they do not decode or control an entire plugin merely because it loads.

## Scoped support

| Plugin / feature | Newly writable / observable | Real native validation | Remaining boundary |
|---|---|---|---|
| Sytrus Default family | Existing FM/RM/OUT, ratio/SH/32harmonics/VOL plus OP→F1/F2/F3, OP/filter→FX/OUT and source PAN; enabled four-point filter CUT envelope. Existing host controls handle cutoff amount, chorus, etc. | Additive baseline→filter→CUT envelope→FM/filter; independent pan and internal chorus/FX branches. Planned→native saved→cold semantics; complete native sound equality; five auditions per branch. | Only two anchored layouts. Filter types, Send to Next, arbitrary envelope topology, phases and all hidden modulators remain outside the deep codec. Raw envelope time is not seconds. |
| 3xOsc | Named waveforms, coarse semitones/fine cents, mixes; native family pan/phase/detune/random phase and enabled native VOL envelope. | Single sine, detuned saw pair, pluck. All save/cold checks and actual fixed-context audio. | Factory44byte layout lacks native460byte fields; native-save first. Sample waveform needs its own resource and is rejected here. Mix knobs are ratios, not independent linear amplitudes. |
| Maximus | Low/Mid/High/Master transfer curves; separately addressed effect-host normalized transactions for gain/timing/crossovers/etc. | Low and Master controlled native UI calibration; mid/high isolated-band audio controls; Master pre-gain47 normalized0.6 cold-read back. | First/default active curve banks only; spare banks preserved, no A/B switching. Graph coordinates are normalized native log-level positions, not asserted dB. Other host parameters require discovery and their own evidence. |
| Fruity WaveShaper | Validated curve points/tension plus pre/mix/post raw controls. | Gain-only false hypothesis retained; revised saturation and saturation→Delay3 actual audio, save/cold state. | Existing polarity/oversampling retained. Reachable input range matters; no generalized curve modes. |
| Fruity Delay3 | Named serialized controls; tempo-sync `time_steps` with1/48step resolution. | Musical echo/combo and isolated pulse;375ms expected vs374.15ms measured at120BPM; alternating L/R repeats. | Raw knobs are not inferred physical Hz/ms/%. Discrete model/filter/limiter fields require native semantics; not every combination validated. |
| Edison | Embedded PCM/cue read/export/replace, deterministic CLI trim/gain/normalization. | Native save/cold **exact decoded PCM and region equality**. Also an observed actual Edison Normalize action changed peak0.501187→1.0; exported native result was restored and rerendered. | CLI PCM DSP is not the Edison processing engine. Only the observed native Normalize action is validated, not denoise/convolution/recording/all editor tools. |
| Slicex | DeckA/B embedded PCM, standard cue regions and ordered Default-family import. | One-region baseline vs three regions; real keys60/61/62 produce measured65.4/130.8/98Hz matching source slices. Exact PCM+cue save/cold checks. | Arbitrary existing trigger/articulator maps, time-stretch algorithms and all UI operations are not decoded. `expected_import_key` is an import convention, not an observed custom mapping. |
| Note articulation | Named `slide`, `porta`, `muted`, `color` on note input/transform; readable `notes articulation`. Raw compatibility retained. | Native Slide in Sytrus/3xOsc; different-color control; mono-portamento with raw1660 and overlapping ordinary notes. Native marker persistence and complete reopen/audio. | Mono itself glides overlapping notes: marked-porta examples do not isolate the marker's independent necessity. Third-party VST slide behavior is not universal. |

Existing generic host control, Surge XT evidence, EQ2/Reeverb2/Limiter etc.
remain supported at their documented scope. No binary, factory preset or new
plugin dependency is bundled. Inspect the **actual current state** with
`sound-design support` and `plugin design-inspect`, not the installed plugin list.

## Saved edits and native acceptance

```powershell
& $fl plugin design-inspect --project saved.flp --channel 0
& $fl plugin design-edit --project saved.flp --channel 0 --request oscillator.json --output new.flp
& $fl plugin design-inspect --project saved.flp --track 1 --slot 0
& $fl plugin sample-export --project slicex.flp --channel 0 --deck a --output slices.wav
```

`design-edit` produces a saved copy and file readback, not a live GUI mutation
or native audio acceptance. For the full loop use an existing sound-design task:

```json
{
  "id":"shaped-echo",
  "parent":"dry",
  "description":"Reachable nonlinear curve followed by rhythmic stereo echoes",
  "mechanisms":["transfer-curve saturation","three-step echo"],
  "fx_chain":[{"slot":0,"preset":"ABSOLUTE/WaveShaper/Default.fst"},{"slot":1,"preset":"ABSOLUTE/Delay3/Default.fst"}],
  "effect_designs":[
    {"slot":0,"design":{"points":[{"x":0,"y":0},{"x":0.015,"y":0.03},{"x":0.04,"y":0.05},{"x":0.1,"y":0.06},{"x":1,"y":0.08}],"pre_raw":256}},
    {"slot":1,"design":{"time_steps":3,"controls_raw":{"model":2,"offset":4500,"feedback":1800,"output_wet":2800,"output_dry":6000}}}
  ]
}
```

Candidate sections: `generator_design`, `effect_designs:[{slot,design}]`,
`effect_host_params:[{slot,param,value,expect?}]`; the latter uses finite0..1
host values with independent name/identity/value checks after reopening.
They complement existing `sytrus_design`, `sytrus`, `fx_chain` and `effect_params`.
Effect editing requires a dedicated insert; no shared bus is silently replaced.
An FL save focus bug was fixed: own-worker saving focuses the host Playlist so
Slicex/Edison do not intercept the command as “Save sample WAV”. Controller
extension is now `fullstack-7`.

## Slide and portamento

Slide notes target an already sounding same-color native voice. Their own
length specifies transition time, and they do not act like a separate ordinary
trigger. At120BPM/PPQ96 this moves from raw key36 toward48 over half a second:

```json
[
  {"key":36,"start_tick":0,"length_tick":288,"velocity":100,"color":0},
  {"key":48,"start_tick":96,"length_tick":96,"velocity":100,"slide":true,"color":0}
]
```

For overlapping ordinary notes, use channel settings
`{"polyphony":{"mono":true,"porta":true,"slide_raw":1660}}` inside the existing
channel `settings` request. `slide_raw` is nonlinear0..1660, **not milliseconds**;
500 glides too fast to be obvious in this fixture,1660 is a deliberately slow
verification value. Sytrus's own `portamento` host control is separate.
`porta:true` on a note marks it without modifying the channel mode; save/readback
of that marker does not establish its independent musical effect in every mode.
`notes articulation --project FILE --pattern 1 --channel 0` exposes flags readably.
Use `audio analyze --purpose pitch` on an actually monophonic dry solo to verify.

## Reproduction and evidence

The local delivery `flstudio-producer-1.2.0` contains original authored context,
candidate FLPs, raw solo/context WAVs, observations, requests, portable rebased
known samples, and `manifest.json`. Source project and user FL editor were
preserved. The embedded Edison/Slicex sample does not depend on its import path.
Native save/cold failures stay failures; an early Edison capture correctly
rejected a worker opened before task sample paths were rebased.

Nine concise invariant tests cover existing state/transaction/preview behavior
plus articulation-bit preservation and gain-vs-timbre/unknown-pitch diagnostics.
Real-FL case evidence is separate from these tests. Cases are technical and
mechanism verification, not a listening contest or broad artistic preference
claim. See [signal methods and measured observations](audio-analysis.md).
