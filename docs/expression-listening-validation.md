# Expression and native listening validation

Windows x64, licensed FL Studio Producer26.1.6.5639, CLI1.3.0.dev0,
local DSH preset2.5.0; 2026-11-02 Asia/Shanghai. The formal patch release remains
[v1.2.1](https://github.com/LiweiDonVee/flstudio-cli/releases/tag/v1.2.1).
The following additions are subsequent development, not changes to that tag.

## What ran in real FL

| Flow | Result | Limit of the evidence |
|---|---|---|
| Sytrus OP VOL KEY/VEL/Mod X/Mod Y | Four separate controlled-input native experiments; readback and changed WAV | Default-family existing two-point maps; not all modulation graphs |
| Sytrus filter CUT same four sources | Four separate native experiments with other inputs fixed | Actual cutoff response depends on filter routing/offsets and other maps |
| Eight-map complete sound | Saved by FL, edit worker stopped, cold-opened in another worker, complete selected sound checked, rendered | Single-Sytrus musical phrase; its solo/context comparison is not a busy-arrangement fit test |
| Polyphonic X crossfade | Opposite OP1/OP2 VOL maps, independent X endpoints on overlapping notes, cold-save/readback and native WAV; intended components within .00003dB of individual notes | Endpoint independence in the controlled sine fixture, not arbitrary mapping curves |
| Five preview scopes | Native timbre, Pattern, Piano Roll, Mixer and Playlist tracks, full song | Scope receipts distinguish generator/insert/song processing and timing |
| Sidechain retention | Authored kick drives saved Fruity Limiter COMP sidechain on sustained bass | Known saved Mixer graph, not opaque plugin/MIDI dependencies |
| Unsaved private session | Native checkpoint captured Mixer level12800→6400 while source disk FLP stayed unchanged | Applies to owned CLI sessions, not arbitrary open user instances |
| Stage-track mute | Native mute/save/unmute isolated e238 track byte; prepared test track enabled and rendered non-silent | Demonstrates the source-mute case, not arbitrary corrupt projects |
| Overridden send automation | Isolated Mixer output with original Master-send automation equals baseline PCM | Only intentionally overridden sends/control links are detached in the preview copy |
| Resource cache invalidation | Same FLP, external sample contents changed: both stale-cache paths rejected; fresh native render fundamental doubled110→220Hz | Known channel-sample fingerprints; plugin-managed resources/binaries remain opaque |
| Portable restoration | Four shipped FLPs rebound with bundled authored sample and natively rendered again | Context, neutral and polyphonic reference PCM exact; expressive comparison differs only by preview gain and PCM quantization residual8.52e-5 |

Sidechain settings were set and observed in a CLI-owned native worker, then
saved/closed/reopened: hidden selector chose **Insert3 by menu identity**, not
the mistaken assumption that its selector value equals Mixer index3. COMP
threshold -28.9dB, ratio9.4:1, attack0, release306.42ms; Limiter ATT0 avoided
lookahead ambiguity in this particular timing fixture. Relative bass gain was
-5.1048dB at kick+20ms, -1.7341dB at70ms and recovered by120ms. The Playlist
lead+bass preview versus isolated lead plus retained-duck bass had residual
-74.2517dB in this linear-Master fixture. This is evidence of preserved control
behavior, not a universal stem-summation guarantee.

## Actual native model input

The installed DSH runtime mounted `listen_audio` in both real presets. Seven
successful production-tool calls plus an earlier direct route check sent actual
WAV/MP3 bytes through Gemini `generateContent`. Audio parts, hashes, MIME, request
size/hash, HTTP200 and model request IDs were recorded. The model in the local
route was `gemini-3.8-flash`; text agents obtained its attributed observations.

- A neutral A/B question distinguished the standalone Piano Roll's articulated
  voice from a Pattern containing an additional sustained bass.
- A matched Sytrus A/B asked for attack/sustain/register differences without
  asking a particular candidate to win. A separate MP3 song versus Mixer and
  timbre versus Playlist comparison exercised the other input scopes/formats.
- Some descriptions were incomplete or questionable, and some long responses
  reached the provider token limit. Actual input transport and attributed model
  observations are established; exhaustive layer detection, exact timestamps,
  human preference agreement and superiority to a human ear are not.
- The final tool records finish reasons/truncation. No provider, secret or
  protocol can be chosen in model arguments. An undeclared audio-input route
  returned `unsupported`; altered audio SHA returned `failed` before a request.

DSH's current conversation history still does not carry native audio messages.
The listening call is separate and explicitly returns
`agent_received_audio_directly:false`. Original WAVs and signal analysis remain
available when that route fails or its interpretation is uncertain.

## Delivery and repeatability

Local authored material: `outputs/flstudio-expression-listening-20261102`
under the workspace, with four complete FLPs, their restored forms, all scoped
WAVs, the MP3 listening copy, matched references, requests, `restore.py`, receipts
and SHA256 checksums. No private user song, factory preset file, screenshot of
recent projects, plugin binary or credential is included.

Source/candidate observations remain in `.lab/iteration-20261101` for local
inspection: `mapping-calibration`, `mapping-task`, `mapping-comparison`,
`final-native-proof.json`, `focused-preview-checks/proof.json` and listener
receipts. These local evidence directories are deliberately not shipped in the
Python wheel. The public adapter and generic config are under `integrations/dsh`.

Eleven focused repository checks and both Skill validators pass. Existing user
edits to `AGENT-USAGE.md` and `docs/fullstack.md` are preserved. Source Skills
were copied and hashed against both local homes and the linked preset package;
the actual installed CLI reports1.3.0.dev0. A fresh isolated DSH runtime loaded
the same installed linked preset. The running user's Desktop was not forcibly
restarted or globally reconciled: its loaded registry is not claimed updated.
Reload DSH before creating an agent from the new preset; existing conversations
retain their mounted old prefix/tools.

A real main agent called `design_sound`; the actual isolated sound-design child
called `listen_audio`, wrote its verified candidate report, and sent the result
back. The first acceptance host reached its nine-minute limit after child
completion. Three same-session continuation attempts on the original text
route failed upstream before tools ran. The same parent session then resumed
on the already configured Gemini text route and completed its attributed main
receipt. No sounds, listening or FL work were repeated for that recovery.
`dsh-listening-handoff-proof.json` retains the initial host interruption;
`dsh-main-recovery-proof.json` records the successful continued lineage.

The final production tool also saved an exact receipt through `output_file`.
Saved/returned JSON matched; addressing that existing output failed before a
second native request. The complete flat receipt was passed directly to
`sound-design report`, which produced a compact two-candidate handoff with input
hashes and the receipt path. The report indexes listening evidence instead of
embedding a second copy of the complete model response.
