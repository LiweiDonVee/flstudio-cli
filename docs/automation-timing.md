# Automation timing and pitch diagnostics

Saved curve points use beats local to their source Automation Clip, not global
song time. For a point visible in a clip's source window:

```text
song_beat = clip.start_tick / PPQ + point.position_beats - source_window.start
seconds = song_beat * 60 / BPM  # constant tempo only
```

`playlist list` reports Automation source windows in beats; `playlist edit`
accepts `source_start_tick` in ticks. For example, moving a Pattern originally
at beat32 to0 does not translate separately linked Automation Clips. To audition
the original32..64-beat automation beside that excerpt, put the Automation Clip
at0, set `source_start_tick:32*PPQ` and `length_tick:32*PPQ`. Alternatively crop
and translate its points, retaining the evaluated values at both boundaries.
Keep pre-roll, sustained notes and effect tails when the musical phrase needs
them; these edits alone do not reconstruct arbitrary boundary state.

Before diagnosing a silent pitch curve:

1. Resolve the saved target address to its channel IID, then identify which
   channel actually plays the measured note. A multisample melody may move
   between many Sampler channels.
2. Check the active arrangement, Playlist track enable, clip mute and source
   window. Automation links and point readback establish saved structure only.
3. Render an unmistakable held-note pitch change on that actual voice, keeping
   the full project's object identities. In the calibrated native Sampler case
   with raw range0..12800, `.5→.45` gives approximately−480cents. Do not transfer
   that scale to arbitrary plugins or controller ranges.
4. Then test the intended expression on a matched dry solo. Compute cents with
   `1200*log2(after_hz/before_hz)`. Exclude nulls and overlapping voices; short
   analysis windows and modulated effects require an unchanged-repeat baseline.
   A fast glide can itself cause low-periodicity nulls in a long window. Shorten
   the window with a known lower pitch bound, still covering at least three
   periods at `min_hz`; do not fill nulls or lower confidence to manufacture a
   passing measurement.

Since1.2.1, `automation create` clears the
mute bit on its newly created clip rather than inheriting an existing clip's
mute state. Existing records, other flags and opaque tails are preserved. It
does not enable a muted Playlist track or change the selected arrangement. The
single offline regression covers both source mute states and saved readback;
it is separate from the real-engine pitch/timing evidence.
