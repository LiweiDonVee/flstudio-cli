# FL Studio CLI

Compose and edit saved FL Studio projects, render with the real FL engine,
and optionally control an open session through a configured local MIDI bridge.

Windows x64, Python 3.12+, tested with FL Studio Producer **26.1.6.5639**.
The project does not bundle FL Studio, its factory templates or plugins.

## Install and make a beat

Install [uv](https://docs.astral.sh/uv/), then:

```powershell
git clone https://github.com/LiweiDonVee/flstudio-cli.git
cd flstudio-cli
uv tool install --editable . --python 3.12
flstudio doctor
flstudio project build --request examples/beat.json --output my-beat.flp
flstudio project inspect --input my-beat.flp --summary
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

The file backend supports explicit pattern/channel notes, fixed-layout Playlist
pattern clips, sample paths, installed generator/effect `.fst` presets,
channel levels and routing, and Mixer levels, names, mute and bus routing.
Every edit creates a new file; existing outputs and source files are never overwritten.

[Request format and units](docs/quickstart-0.2.md) · [Agent quickstart](AGENT-USAGE.md)

## Parameter state and actual audio response

```powershell
flstudio plugin params --project song.flp --track 0 --slot 9
flstudio plugin verify --project song.flp --track 0 --slot 9 --param Emphasis --value .25 --output-dir checked
```

`checked/project.flp` changes only the requested parameter. Separate diagnostic
copies run the copied effect before/after the change with the same controlled
input and are rendered by FL itself. The result identifies this isolated
verification context; it does not imply the open editor changed.
The saved-state profile currently covers Emphasizer v2 **Emphasis** only.

## Optional live control

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
Arbitrary automation curves, unknown variable-layout Playlist clips and custom
third-party plugin controls are outside the current implementation.

Three workflow regressions are maintained; native application and independent
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
