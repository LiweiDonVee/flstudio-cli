# DSH native audio listener

`listen-audio.js` is a Node-built-in-only DSH plugin. Mount it in both the main
FL Studio preset and the dedicated sound-design child. It registers
`listen_audio`; this is a separate native model call, not an audio-message
extension to DSH's current text/image/file conversation history.

Example scoped plugin entry (use your own installed package/module path):

```yaml
- id: tool-listen-audio
  name: /absolute/path/to/listen-audio.js
  config:
    provider: audio-provider-id
    model: actual-audio-capable-model
    protocol: gemini-generate-content
    baseURL: https://your-provider.example
    credentialRef: YOUR_AUDIO_API_KEY_REF
    audioInput: true
```

Register the secret separately in DSH credentials. The tool resolves only that
configured reference; agent arguments contain no endpoint/model/secret. An
OpenAI-compatible text route with an audio-sounding model name is insufficient.
This adapter currently implements Gemini's `/v1beta/models/MODEL:generateContent`
native inline-audio protocol only. Provider route compatibility must be tested.

Main agent or child tool arguments:

```json
{
  "preview_manifest": "E:/work/listen-01/preview.json",
  "question": "Does the lead obscure the bass attacks at 2–4 seconds? Describe audible evidence and uncertainty.",
  "output_file": "E:/work/listen-01/listening.json"
}
```

Optional `artifact_id`, `reference_manifest` and `reference_artifact_id` select
an A/B comparison. A `sound-design compare` manifest exposes IDs such as
`candidate-a:solo` and `candidate-b:solo`; `audition.json` uses `context-1` or
`solo`. The CLI's new comparison manifests include explicit hashed artifacts;
old comparisons can be regenerated from existing audition WAVs.

The tool validates a ready manifest, regular audio files, MIME/container,
SHA256, bytes and bounded payload before resolving credentials or sending audio.
It returns the provider/model/request ID, exact input hashes, conversion and
coverage, native request size/hash, observations and listening attribution.
Failure is `failed` or `unsupported`, never a successful signal-only substitute.
`agent_received_audio_directly` remains false.

Default cap:12MB per artifact,18MB total encoded request. Use CLI `encoding:mp3`
or bounded windows for longer audio. Input audio goes to the configured provider:
use it only where the user/task authorizes that audio's transmission.
Retain original WAVs and compare level-matched audio for taste decisions.
For long songs record all evaluated intervals; a whole-file transmission does
not establish exhaustive model attention. See [preview scopes](../../docs/audio-preview.md).

Local acceptance used the installed DSH runtime, real mounted main/specialist
presets, Gemini native WAV and MP3 calls, and authored FL music. The validated
CLI repository copy and the local preset's module are byte-identical at sync.
Reload the definitions in DSH before creating an agent from the new preset.
Changing a linked bundle's files alone does not guarantee that the running
Desktop reloads its registry. Existing conversations retain their prior tools.
