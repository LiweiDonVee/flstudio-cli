# Recover the 1.1.0 sound-design examples

The WAVs play without FL Studio. Editing or rerendering requires Windows,
FL Studio (verified: Producer 26.1.6.5639), Sytrus, Fruity Reeverb 2 for the
reverberated lead case, and Surge XT VST3 for the arrangement's pad. The tested
Surge build is official 1.4.0 nightly `dab78c6170732b3883216e569a84bf084ae0ea97`.
Different builds or unresolved VST3 module paths require a local compatibility
check; do not assume byte-identical restoration. No plugins or licenses are bundled.

## 1. Install the CLI

Install from the v1.1.0 source as described on the Release, or install the
included wheel into a Python 3.12+ environment:

```powershell
python -m pip install .\flstudio_cli-1.1.0-py3-none-any.whl
```

NumPy is optional for restoring/editing files, and required for audio analysis.
The source installation's `.[sound-design]` extra installs it.

## 2. Rebind samples into a new saved copy

Run this PowerShell block from the extracted archive root. Change `$source`
to another delivered FLP if needed; every musical case keeps drums at channels
3, 4 and 5. Choose a new `$output` path each time. This only edits sample paths;
it does not replay synthesis operations or change notes.

```powershell
$root = (Get-Location).Path
$source = Join-Path $root 'selected.flp'
$request = Join-Path $root 'sample-relocation.json'
$output = Join-Path $root 'selected-local.flp'
if (Test-Path -LiteralPath $output) { throw 'Choose a new output filename.' }
@{ channels = @(
    @{ index = 3; sample_path = (Join-Path $root 'assets\kick.wav') },
    @{ index = 4; sample_path = (Join-Path $root 'assets\clap.wav') },
    @{ index = 5; sample_path = (Join-Path $root 'assets\hat.wav') }
) } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $request -Encoding utf8
flstudio project edit --input $source --request $request --output $output
```

Open `selected-local.flp` in FL. If FL cannot resolve Surge XT, locate the
installed matching VST3 using FL's missing-plugin dialog or plugin database;
preserve the saved plugin state rather than replacing the sound with an init.
Reopen/save a new copy and compare a native render with the supplied WAV before
treating a different plugin build as verified. Hidden plugin resource paths
cannot be generically rebound; these designs use no external plugin samples/IRs.

## 3. Choose a starting point

- `source.flp`: authored four-bar, six-part, 110 BPM, 96-note reference.
- `cases/GROUP/ID/project.flp`: complete native selected sound in the arrangement.
  `cold-reopened.flp` is its independent restored state; `before.flp` and
  `operation.json` retain the previous sound and the scoped design operation.
- `selected.flp`, `undone.flp`, `continued.flp`: specialist choice, original sound,
  and the same chosen sound with a 295.2 ms release revision.
- `dsh-execution/chosen.flp`: a real DSH main-Agent application after delegation;
  `chosen-context.wav` is its native render. This project needs the same rebinding.
- `comparisons/GROUP/solo` and `context`: same-order constant-gain RMS-matched
  comparison audio. Raw audio remains in each case. Matching is not a listening
  judgment or guaranteed equal perceived loudness.

`manifest.json` indexes curated files. Evidence JSON intentionally retains the
original development paths for traceability; those paths are not required to
load the complete delivered FLP. For a new revision, run `sound-design prepare`
on your recovered copy and use the bundled Skill. Do not pass an old evidence
file to `--task`: make a fresh local task with correct identities and resources.

See `docs/support-matrix.md` and `docs/validation.md` for what was actually tested.
Listening was not performed; recommendations are provisional.
