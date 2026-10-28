# FL Studio CLI 1.0.1

This patch release improves long-running Agent sessions and failure evidence without changing the saved-project write contract.

- `project snapshot --output` writes a reusable, schema-tagged baseline; `--since` returns bounded changes and explicitly reports sections that were omitted from either view.
- A failed live write attempts a readback-confirmed rollback to the value observed before the write. The result records `rollback.attempted`, `rollback.confirmed`, and any rollback error.
- Mixer automation validates the source track before indexing it, so an invalid `mixer_send` target returns a normal input error instead of a traceback. Automation values now use the documented inclusive `0..1` range.
- `audio inspect` exposes aggregate and per-channel `peak_dbfs`, `rms_dbfs`, and `crest_factor` alongside the original PCM values.
- The saved-project semantic diff now includes Playlist entries without raising an internal `NameError`.

Validation on the release checkout:

```text
python -m compileall -q src
python -m pytest -q -p no:cacheprovider   # 4 passed
```

The snapshot baseline/delta path and the audio fields were also exercised against FL Studio's installed `NewStuff.flp` and a real rendered WAV. No user FL Studio process or project was modified.
