# Real sound-design validation — 2026-11-01

## Conditions and acceptance

Actual FL Studio Producer **26.1.6.5639**, Sytrus from that installation, and
installed official Surge XT VST3 **1.4.0 / nightly dab78c6**. Operations used
independent CLI-owned private FL workers and native FL batch rendering, without
manual intervention in the candidate/render pipeline. The user's project was
not a fixture. No listening-capable evaluator was available.

Before implementation, the acceptance work was defined as: real parameter
write/readback → audible-signal change → complete native save → cold reopen →
rerender; two different plugin/control paths; three musical roles with several
mechanisms; independent specialist handoff/application/continuation; and actual
failure/recovery. These are technical gates, not subjective music ratings.

The musical fixture is a newly authored four-bar **110 BPM**, 96-note excerpt:
bass, lead, three-note changing pad chords and three sampled drum parts.
Velocities, register, short lead gates and pad rests vary within the phrase.
Its length is **8.7273 s**, plus retained release tails. This is one real arranged
excerpt, not evidence across many genres or a user's entire production.
Rebuild it with `uv run python examples/sound-design/build_context.py
--output-dir NEW_DIRECTORY` (set `--surge-preset` for a different local path).
The script uses authored repository drum samples and requires locally installed
plugin presets; it neither downloads nor bundles FL or a plugin binary.

## Mechanisms accepted by actual Sytrus

Single-variable native/UI calibration and four controlled WAV cases established:

- Matrix direction is target row/source column. Native saved matrix/ratio/SH/
  harmonic/envelope fields passed 24 recorded checks, with a separate cold save
  retaining the entire native plugin state.
- With the same raw FL key 36, ratio 1 and 2 produced approximately **65.441 Hz**
  and **130.882 Hz**. Note labels/ratio must not be inferred from generic MIDI
  octave conventions.
- Requested harmonic 2/3/7/16/32 amplitudes .5/.25/.15/.12/.1 produced measured
  relative amplitudes **.500366/.250158/.150122/.119968/.100088**.
- Fast versus slow enabled envelopes changed early 20–80 ms RMS from
  **.081824 to .039047**. A late 1.0–1.1 s window changed from zero to **.005461**.
  These measurements validate mechanism, not a listening word or raw-time-to-ms
  formula. Factory Default has VOL ENV disabled; editing points alone was an
  unsuccessful initial hypothesis and is not a final candidate.

Evidence lives under `.lab/sound-design/sytrus-adapter/`: native paired states,
`audio-calibration.json`, and `acceptance-131338/report.json`, `second-cold.json`.
The [adapter scope](sytrus.md) describes both validated Default layouts.

## Three roles and preset-only controls

Each role has an unchanged preset control and three mechanism directions.
Final candidates all have actual native complete-state restoration and solo/
context/repeated/reopened WAV evidence. Raw solo levels differ deliberately;
comparisons also provide constant-gain matched previews.

| Role | Design directions | Solo RMS dBFS |
|---|---|---|
| Bass | Sytrus transient FM; Sytrus 1.5:1 RM edge; Surge subtractive/envelope | −25.73 / −25.26 / −25.46 |
| Lead | Sytrus FM pluck; additive harmonics; Surge dual oscillator + low-wet Reeverb2 | −38.11 / −31.58 / −30.30 |
| Pad | Sytrus soft additive/unison; independently delayed FM brightness; Surge filter/amp-envelope body | −32.21 / −33.04 / −30.98 |

Unmodified controls were −24.24 / −27.62 / −32.39 dBFS. This table is not a
ranking: the shorter bright pluck has a different envelope and crest factor.
No sample clipping occurred in the final solo/context renders. Low-output
Surge alternatives were revised using measured VCA gain. An excessive Sytrus
pad level correction was subsequently reduced in a new task; its final solo
level is −32.21 dBFS, with context peak −8.51 dBFS. Gain corrections do not count
as distinct synthesis directions.

Primary evidence: `.lab/sound-design/{bass-task,lead-task,pad-task,pad-level-task}`
and the final role comparison directories. Sytrus pad level continuation retains
the same synthesis state and fixed actual accompaniment. Final native plugin
blobs are identical after cold reopen. Reopened context level differences from
same-state references were **0–0.110 dB**; individual PCM samples can differ
because the accompaniment includes randomized oscillators. Tolerances are
reported alongside repeat variability, not advertised as perceptual equivalence.

Preset-only workflow comparison:

| Question | Observed result |
|---|---|
| Technical delivery | 9/9 final designed candidates and 3/3 unchanged controls passed native state/audio checks |
| Actual mechanism change | Native Sytrus paired calibration plus different FM/RM/additive/subtractive/envelope branches |
| Operation time | Unchanged-control candidate save/reopen ≈3.6 s; five-render audition ≈13.6 s locally; designed branches of similar size use the same pipeline |
| Human takeover during candidate/render operations | 0; the isolated workers were controlled by CLI |
| Musically usable proportion / contextual preference | Unknown: no listening evaluation |
| Time to a satisfactory sound | Unknown: synthesis execution time is not satisfaction time |

The unmodified Default controls are a narrow preset-only reference, not a broad
contest against an expert choosing presets. No superiority claim follows.

## Independent specialist and a second assignment

The main Agent prepared `independent-pad-task/task.json`; a separate specialist
read the Skill and independently produced six branches, 30 native renders and
three final directions: warm wide backing, centered sine body and RM texture.
It found quiet/mono initial attempts and corrected them through new branches.
All 96 notes, other voice states and accompaniment PCM were retained.
Its recommendation is explicitly provisional, with `listening:not_performed`.

The main Agent applied its `sp-warm-wide-r2` delivery to a new FLP, saved and
cold-reopened it, and rendered it. Complete target state remained equal; other
channel event records and all notes were preserved. Undo produced **zero parsed
semantic changes** relative to the source. Raw FLP bytes differ through control
record ordering, which is not claimed to be byte-exact undo. Applied-versus-
delivered audio differed by .0484 dB RMS with spectral cosine distance .0000494.

The main Agent prepared a new task from that applied project and returned it to
the same specialist: keep the identity/width, shorten release. The specialist
delivered **727.0 / 295.2 / 205.9 ms** alternatives. Among 918 observed host
parameters, only Release index 334 changed. At the last 50 ms before the next
chord, the 295.2 ms choice reduced residual RMS by **32.49 dB**; 205.9 ms reached
digital silence. Accompaniment is also silent in those windows, so this measures
reduced old-chord spill into rests, not improved masking. The main Agent applied
the provisional 295.2 ms revision to another editable FLP.

Evidence: specialist `result.json`/integrity/transition records in
`independent-pad-task` and `pad-continued-task`; main proof is
`main-specialist-handoff-proof.json`, with `specialist-continued.flp` as the
continued result. No result is an invented subjective audition score.

## Failures and recovery

Actual runs rejected out-of-range normalized values before starting FL, an
absent parameter, an unavailable preset, and an unsupported Sytrus layout.
Surge Scene Mode echoed .37123 but cold-reopened at .335: candidate remained
`unconfirmed`. A real one-second render timeout was retained and successfully
resumed. Killing the owned coordinator during editing left its private worker;
the same candidate's concurrent resume was rejected, then normal resume stopped
that exact old worker and completed attempt two, including audio.

An interruption between successful rendering and analysis was reproduced by
removing just that analysis record. Resume reused unchanged WAV bytes and
completed the missing analysis. Native capture accepted an actual plugin
envelope edit and retained complete state; a subsequent tempo change was
rejected as context pollution. Separate native baseline saves advance work-time
metadata; only those timer fields are excluded from capture comparison.

Pure state/signal regression checks remain **7 tests** total, including the
existing suite. New assertions cover full opaque/FX transfer and undo, IID
resolution after channel reordering, invalid-value preflight, and non-destructive
preview matching. They supplement the actual FL evidence rather than replace it.

Long-iteration observation also has a small reproducible check: full Sytrus
design inspection was 4,477 UTF-8 bytes; selecting operator 1 with `--summary`
was 1,593 bytes, retaining its same ratio and listing every omitted operator/raw
point scope explicitly. Task `status` exposes the branch/audio summary with
detailed logs left on disk. The applied specialist sound also passed a saved
redo after undo, with identical target state to the selected version.
The specialist's original handoff was 51,762 bytes. `sound-design report`
indexed the same three native states, audio, FX/resource/evidence paths and
provisional choice in about 8.4KB, leaving full observations available on demand.

## DSH deployment evidence and limits

Preset package **2.3.0** retains stable main id `fl-studio`, adds fixed
`design_sound → fl-studio-sound-designer`, followup/list tools and scoped Skill
discovery. Actual Electron-bundled **DSH 0.2.1-rc.5** in an isolated profile
created both real Agent contexts. Main exposed `design_sound`, `send_message`,
`list_agents`; child read the installed Skill and had no recursive spawn tool.
That admission check sent **zero model requests**. A separate real DSH model
run then used the locally configured **pin-cn / deepseek-v4.1-flash Max** route.
The main Agent actually called `design_sound`; its child session header names
`fl-studio-sound-designer` and its parent. It independently delivered an
unchanged reference, transient FM and additive-harmonic bass, all with native
state equality and five verified auditions. Solo levels were −24.24 / −26.24 /
−26.41 dBFS, with no sample clipping. These are signal observations, not taste.

The real DSH main Agent applied the FM branch and rendered `chosen-context.wav`.
Independent checks found its complete target state equal to the delivery, all
96 notes and other channel events retained. Render level differed by .02046 dB
from the chosen candidate reference; spectral cosine distance was .0000894.
An upstream `PI_AI_ERROR` interrupted the final receipt. The same persisted
main session was resumed and completed the compact handoff using the new
`sound-design report` command; no sound edits or renders were repeated.

Evidence: `.lab/sound-design/dsh-independent-delivery-proof.json`,
`dsh-model-recovery-proof.json`, and `dsh-delegation-task/{result.json,
dsh-main-result.json,chosen.flp,chosen-context.wav}`. The first musical child
above used this coding Agent's delegation; this additional run used DSH itself.

Local desktop deployment was synchronized after development: installed CLI
**1.1.0**, linked preset package **2.3.0** appearing once in the desktop bundle
list, and both Skills byte-equal to package sources. DSH was cold-launched into
a new window after it had closed. Native screenshot capture still timed out,
so a click through the new-session preset menu is not claimed. Existing chats
retain their preset generation; use a new FL Studio chat for the new tool set.
The exact deployment record is `local-dsh-sync-proof.json`.
