# Addressed native audio and model listening

`audio preview` renders a new prepared copy through real FL and writes a small
`preview.json`. It identifies exactly what was rendered and which WAV/MP3 bytes
a listening model should receive. It never edits the source project.

```powershell
flstudio audio preview --project song.flp --request listen.json --output-dir listen-01
# For unsaved edits in a CLI-owned worker, checkpoint first:
flstudio audio preview --session work/session.json --request listen.json --output-dir listen-02
```

Use one explicit request:

| Target | Request | Meaning |
|---|---|---|
| Timbre | `{"scope":"timbre","channel":0}` | Declared short/held C test notes, generator/internal FX through neutral Master; custom `notes` supported |
| Pattern | `{"scope":"pattern","pattern":1}` | All its voices and Pattern events, standalone |
| One Piano Roll | `{"scope":"piano_roll","pattern":1,"channel":0}` | Explicit Pattern and channel, never the currently focused window |
| Mixer insert/bus | `{"scope":"track","kind":"mixer","track":2}` | Post-insert/fader output, input ancestors retained, directly to neutral Master |
| Playlist lane | `{"scope":"track","kind":"playlist","track":1}` | Selected music clips in their native song positions, song controls retained |
| Song | `{"scope":"song"}` | Selected arrangement with its mix and automation |

Channel/Mixer indices start0; Pattern and Playlist track numbers start1.
`arrangement` selects an explicit saved arrangement. Default is the saved choice.

Pattern and Piano Roll can add `"occurrence":{"clip_index":N}` to retain a
particular song placement, clip window and Automation Clips. Without occurrence,
the standalone Pattern retains its Pattern events but schedules no song
Automation Clips. `processing:"generator"` bypasses Mixer effects for timbre,
Pattern or Piano Roll; `processing:"mix"` retains the audio route (default except
timbre). Plugin-internal FX remain part of the generator.

Mixer preview excludes the original downstream buses/sends, centers and unmutes
Master at unity, and bypasses its FX unless `master_fx:true`. Mixer0 instead
means Master output and defaults to retaining its FX. An isolated nonlinear bus
or Master is not an exact mathematical contribution to the original mix.

Isolation retains saved Mixer sidechain inputs. Other Pattern occurrences are
copied into control-only patterns where necessary: their controls and sidechain
notes remain without leaking unrelated audible notes. Ambiguous shared-insert
sidechains fail with an instruction to preview the Mixer track or song instead.
Opaque plugin-internal and MIDI control dependencies are not inferred.

## Windows, long songs and cost

Add `start_seconds`/`end_seconds` **or** `start_tick`/`end_tick`. Ticks require an
unambiguous tempo map; seconds work when musical timing is unknown. The engine
plays the complete prepared song before cropping, so earlier automation and
effect history are retained. An occurrence/lane defaults to its song interval.
Extend the bounds into existing rendered tail when needed. No tail is invented.
FL's native export settings, compensation and plugin latency still apply;
tick conversion is not a universal guarantee of sample-accurate transient onset.

`encoding:"auto"` keeps WAV and creates a 192kbps MP3 listening copy above10MB;
`"mp3"` forces that copy and `"wav"` keeps only WAV. Installed FFmpeg is needed
only for MP3. No extra playback gain or normalization is applied by conversion.
The raw native WAV is always retained; encoder padding may differ from frame
duration. Use WAV for short timbre differences and the original PCM for metrics.

Create additional windows/encodings without another FL export:

```powershell
flstudio audio preview --project song.flp --request chorus.json --output-dir chorus-01 --reuse listen-01/preview.json
```

Reuse requires matching prepared project, known channel-sample contents and the
complete WAV hash. A ready output directory can be read again only for matching
source/request/resources/artifact hashes. Changed or partial outputs are kept;
choose a new directory. Plugin-managed sample/IR/wavetable dependencies and
plugin binaries are not exhaustively fingerprinted: use fresh renders when
they change. `--dry-run` plans without a render; a live-session dry-run defers
target validation and does not contact or checkpoint the worker.

## Native audio model handoff

The [DSH adapter](../integrations/dsh/README.md) supplies `listen_audio` to both
the main preset and sound-design child. Pass the absolute ready `preview.json`
and a concrete musical question. It sends actual selected audio bytes, with
hash/MIME/coverage receipts; it also accepts `audition.json` and the level-matched
artifacts in a new `comparison.json`. Optional second manifest/artifact enables A/B.

The current DSH conversation transport does not carry native audio messages.
The adapter calls a separately configured native audio model and returns its
attributed observations to the agent. It explicitly reports
`agent_received_audio_directly:false`. This lets text-only agents obtain actual
model listening without treating a filename, transcript or spectrum as hearing.

Current supported route: Gemini `generateContent` with inline audio. Configure
an actual audio-capable model, HTTPS endpoint and credential reference; the agent
cannot supply an endpoint or secret. Other model protocols return `unsupported`.
The local implementation caps an artifact at12MB and a request at18MB; longer
audio needs MP3 or windows. A full-file receipt records transmitted coverage,
not proof that a model attended to every moment. For a long song, ask bounded
section questions and keep their covered intervals and unresolved gaps.

Listening is subjective model evidence, not an objective quality score. Compare
fixed MIDI/context and level-matched candidates, use controlled signal analysis
for mechanism questions, and preserve uncertainty. An unavailable listener
returns explicit failure/unsupported and leaves audio available for local
analysis or a human; it does not fabricate successful listening.
