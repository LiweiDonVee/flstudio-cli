# FL Studio CLI

Compose and edit saved FL Studio projects, render with the real FL engine,
and control an addressed FL session through a standalone controller.

Windows x64, Python 3.12+, tested with FL Studio Producer **26.1.6.5639**.
The project does not bundle FL Studio, its factory templates or plugins.

Version 1.0.0 is the stable fullstack release. New Automation,
Playlist, session and VST3 workflows are described in [fullstack work](docs/fullstack.md).
Its supported scopes and remaining GUI collaboration boundaries are documented in [release 1.0.0](docs/release-1.0.0.md).

## Install and make a beat

Install [uv](https://docs.astral.sh/uv/), then:

```powershell
git clone https://github.com/LiweiDonVee/flstudio-cli.git
cd flstudio-cli
uv tool install --editable . --python 3.12
flstudio doctor
flstudio project build --request examples/beat.json --output my-beat.flp
flstudio project inspect --input my-beat.flp --summary
flstudio project validate --input my-beat.flp
flstudio project snapshot --input my-beat.flp --focus channels --focus mixer --budget 12000
flstudio render wav --project my-beat.flp --output my-beat.wav
```

If a running terminal has not refreshed PATH, use
`& "$env:USERPROFILE\.local\bin\flstudio.exe"`.
The sample drums in `examples/audio` are generated for this project.

## Saved projects

```powershell
flstudio notes list --project song.flp --pattern-number 1 --channel-index 0
flstudio notes replace --project song.flp --pattern-number 1 --channel-index 0 --notes notes.json --output revised.flp
flstudio project edit --input song.flp --request changes.json --output mixed.flp
```

`project validate` is a read-only preflight for the saved envelope, channel/note references, Mixer routes, Automation links and encode round-trip. It returns a failed result before an Agent hands an invalid artifact to FL.
`project snapshot` emits stable counts and bounded sections for long-running Agent context. Use repeated `--focus` values, `--detail`, `--limit` and `--budget` to expand only what the current step needs.


The file backend supports explicit pattern/channel notes, pattern/audio/automation
Playlist clips with per-record tails, sample paths, installed generator/effect `.fst` presets,
channel levels and routing, and Mixer levels, names, mute and bus routing.
Every edit creates a new file; existing outputs and source files are never overwritten.

[Request format and units](docs/quickstart-0.2.md) · [Agent quickstart](AGENT-USAGE.md)

## Sytrus and complete mixer chains

```powershell
flstudio plugin presets --plugin Sytrus --search bass
flstudio project build --request examples/sytrus-mix.json --output synth-mix.flp
flstudio render wav --project synth-mix.flp --output synth-mix.wav
flstudio sytrus params --project synth-mix.flp --channel 0 --search master
```

Build/edit requests can combine Sytrus native host controls, Channel → Insert →
Bus → Master routing, send levels, and complete effect chains. Load, copy, move,
swap or remove slots while retaining preset state, host overrides, bypass and
wet/dry settings. Saved parameter profiles also cover Parametric EQ 2,
Reeverb 2, Soft Clipper and Limiter controls.

[Sytrus, mixer and FX request reference](docs/sytrus-mixing.md) ·
[1.0.0 release evidence](docs/release-1.0.0.md) · [0.5 native audio evidence](docs/release-0.5.md)

## Parameter state and actual audio response

```powershell
flstudio plugin params --project song.flp --track 0 --slot 9
flstudio plugin verify --project song.flp --track 0 --slot 9 --param Emphasis --value .25 --output-dir checked
```

`checked/project.flp` changes only the requested parameter. Separate diagnostic
copies run the copied effect before/after the change with the same controlled
input and are rendered by FL itself. The result identifies this isolated
verification context; it does not imply the open editor changed.
This dedicated controlled-input verifier covers Emphasizer v2 **Emphasis**.
Sytrus and the other native effect profiles use saved host-control overrides;
their practical audio checks are documented in the 0.5 report.

## Live control and private sessions

Install the standalone FL controller and reload it once in FL:

```powershell
flstudio bridge install-controller
flstudio live status
flstudio live query --command cli_capabilities
flstudio session start --project my-beat.flp --output-dir work-session
flstudio live --session work-session/session.json status
flstudio session save --session work-session/session.json --output saved.flp
flstudio session stop --session work-session/session.json
```

An existing controller binding is retained. A fresh machine must select the
installed controller in FL's MIDI settings once. The standalone controller
uses addressed file RPC; neither an MCP server nor the MIDI relay is required.
Private sessions run their own FL process and leave the user's editor alone.

The older MIDI transport remains optional:

Install the MIDI extra to run the CLI's own local relay:

```powershell
uv tool install --editable ".[midi]" --python 3.12
flstudio bridge start
flstudio bridge status
```

The relay owns the MIDI ports and `127.0.0.1:9787`; no MCP server or daemon is
needed. It uses the installed FL controller's compatible SysEx protocol.
The virtual MIDI ports and FL controller still need their one-time configuration.
On Windows, `bridge start` can launch the installed loopMIDI helper at login.

With FL connected:

```powershell
flstudio live status
flstudio live set-tempo --bpm 130
flstudio live set-mixer-pan --track 1 --value .25
flstudio live plugin-params --track 0 --slot 9
flstudio live set-plugin-param --track 0 --slot 9 --param Emphasis --value .25
flstudio live plugin-params --channel 0 --search Master
```

The client also remains compatible with the local bridge from
[flstudio-mcp](https://github.com/rosasynthesiz/flstudio-mcp).
`bridge stop` stops only a relay identifying itself as CLI-owned.
The saved-project backend works without MIDI dependencies or a relay.

## Result semantics and scope

Commands return UTF-8 JSON. `artifact_ready` means a saved file was written and
read back; `verified_scopes` names the evidence actually obtained.
Native WAV rendering checks new PCM output, arrangement duration, non-silence
and source preservation. Live writes require readback; unresolved values return
`unknown` rather than success. `--dry-run` makes no project/audio changes and
does not contact the live bridge.

File edits do not change the editor's unsaved memory. The collaboration path
is **GUI save → CLI new copy → GUI open the copy**.
Saved Automation curves and host-exposed third-party parameters are implemented.
Exact in-place live Piano Roll editing, recording jobs and dynamic Mixer
expansion have owned-worker paths with native readback. First-use recording and
popup menus require the Agent to inspect and address the private window.
Arbitrary plugin GUI controls remain human-required when no host parameter or
reliable canvas postcondition exists. Unknown Playlist layouts are rejected;
audio fade handles have a native GUI path while no generic offline fade-tail
writer is supplied.

Four workflow regressions are maintained; native application and independent
comparison evidence is documented separately. Development checks require a
local FL installation:

```powershell
uv sync --locked --python 3.12
uv run pytest -q
```

A fresh Astra XHigh comparison rated the 0.4.0 file workflows **CLI clearly better** for
the three tested local tasks: session controls, saved parameter verification,
and a saved beat with native audio output. This does not establish complete
GUI coverage. [Independent report](docs/independent-comparison-0.4.md) ·
[Structured evidence](docs/independent-comparison-0.4.json)

0.4.1 adds the CLI-owned MIDI relay and the DSH migration path; its local
connection checks are documented in [release-0.4.1.md](docs/release-0.4.1.md).

The design drew on [CLI-Anything](https://github.com/HKUDS/CLI-Anything) and
[OpenCLI](https://github.com/jackwener/OpenCLI). This is an independent project,
not an Image-Line, HKUDS or OpenCLI product. [MIT license](LICENSE).
