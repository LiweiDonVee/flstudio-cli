# Sytrus performance mappings

Tested on FL Studio Producer 26.1.6.5639, Windows, 2026-11-02.
This extends the existing Default-family deep adapter; it does not decode every
Sytrus preset. Inspect first with `sytrus design-inspect` or `sound-design support`.

The adapter edits existing **two-point** KEY, VEL, MOD X and MOD Y graphs on
operator VOL and filter CUT. Sources are `key`, `velocity`, `mod_x`, `mod_y`.
Names, endpoints and native curve tension are readable. Existing flags, curve
shape, graph topology, footer and unrelated state are retained.

Example `sytrus_design` section of a sound-design candidate (modify a suitable
parent; this section alone is not a complete FM patch):

```json
{
  "operators": [{"operator": 2, "volume_mappings": [
    {"source": "velocity", "at_min": 0.15, "at_max": 1},
    {"source": "key", "at_min": 0.35, "at_max": 0.85}
  ]}],
  "filters": [{"filter": 1, "cutoff_mappings": [
    {"source": "mod_x", "at_min": 0.1, "at_max": 0.9}
  ]}]
}
```

Map values are raw vertical coordinates 0..1, **not** Hz, dB or universal gain.
The neutral horizontal operator VOL graph is 1,1; neutral filter CUT is .5,.5.
The effect also depends on the other maps, filter offsets, envelope amounts and
audio routes. Mod X/Y here are the individual note inputs, not an assumption
about an unrelated host automation parameter.

For a velocity-sensitive FM sound, keep the carrier relatively stable and vary
the modulator's VOL. This changes FM index as well as possible level; it is not
equivalent to the output volume knob. For filter movement, first route an
audibly rich operator through that filter and establish a useful cutoff range.
Change one source while holding the note's other inputs fixed. Compare short
and held notes, different registers and actual-context audio at matched playback
levels. Register-dependent FM can change non-monotonically.

## Evidence and scope

- Four independent VOL-source experiments varied only their addressed MIDI
  input. On the controlled FM fixture, velocity32→112 changed H3/H1 from
  -11.74 to +11.07 dB; Mod X/Y0→255 changed it from -119.28 to +1.04 dB.
  The unmapped reference stayed near +.94 dB. These are fixture observations,
  not universal transfer functions.
- Four separate filter CUT-source experiments rendered native audio. Mod X/Y
  changed H3/H1 approximately -13.4→+.96 dB with the other inputs held fixed.
- A candidate with eight distinct mappings was saved in real FL, closed,
  reopened in another worker, checked and rendered. A neutral reference was
  retained and comparison previews were level matched without replacing raw WAVs.
- Opposite Mod X→VOL maps on two direct sine operators also passed native
  save/cold reopen. Individual notes and then two overlapping notes carried
  different X endpoints; their intended130.81/392.00Hz components retained the
  individual-note amplitudes within .00003dB. This verifies per-note independence
  and endpoint crossfade in that fixture, not every intermediate curve/polyphony
  setting. The two opposite maps can form a deliberately designed timbre blend.
- Existing factory V2 and FL26-native V3 Default layouts are admitted. Unknown
  layouts, unsupported sources and altered point topology fail before output.
  Arbitrary multi-point maps, random/unison maps, full modulation routing,
  custom phases and filter-type selection remain outside this adapter.

The [validation record](expression-listening-validation.md) indexes the real
projects and audio. The official [Sytrus manual](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/Sytrus.htm)
explains mapping semantics; local experiments establish this implementation's
field identity and sound effect. Neither establishes an aesthetic ranking.
