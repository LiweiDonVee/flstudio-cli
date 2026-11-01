# Practical production guide

This is a decision aid for an Agent working through FL Studio CLI. It does not
replace the user's genre, reference track, taste, or the actual rendered audio.

## Arrangement

Use a section map such as intro, build, main section, contrast, and outro. Keep a
small number of active motifs. Introduce or remove one meaningful layer at section
boundaries and reserve the densest register for the intended peak. Check that every
new Playlist clip has an explicit start and length; repeated material should be
represented by separate clips when the request needs independent edits.

## Drums and bass

Choose the kick's role (sub-heavy or punch-focused) before choosing the bass patch.
Compare their envelopes and fundamental range in mono. Put the snare/clap on a
stable backbeat, then use ghost notes and hat velocity to create movement. Humanize
within the pocket: a few ticks and a modest velocity range are usually more musical
than uniform random offsets.

## Harmony and melody

State the tonal center in the request. Start with a motif that fits the range of its
instrument, then create contrast by changing rhythm, register, or call-and-response.
Avoid filling rests merely because the pattern can hold more notes. Read back the
target pattern and channel after replacing notes so a channel selection mistake is
visible in the artifact.

## Sound design

For a Sytrus patch, name the role and the intended motion. Set oscillator balance
and pitch relationship first, then the volume envelope, then filter/envelope motion.
Use unison and stereo width above the sub range. Save host controls through the CLI
when available; unknown preset-internal values stay unknown. Do not fabricate a
private plugin field from a similarly named knob.

## Mixing and delivery

Balance static levels before adding processors. Cut masking frequencies broadly and
make narrow cuts only when the render shows a specific problem. Prefer shared reverb
sends for a coherent space; automate send level, filter movement, or mute transitions
for structure. Keep low-frequency elements centered and check mono compatibility.

For delivery, render with FL's native worker, inspect duration and per-channel levels,
and listen or analyze the actual WAV. A healthy numeric result is not proof of a
good mix: a clipped sample count, tonal problem, or musical imbalance still needs a
musical decision. If a render is silent or shorter than the project timing, treat it
as a failed artifact and inspect the project rather than raising the master.
