# FL Studio CLI 1.0.3

This patch makes the two long-session observability paths discoverable through `flstudio capabilities`:

- `project.snapshot_delta` describes immutable baselines, bounded comparisons, and the explicit unknown state for omitted sections.
- `audio.inspect` describes the aggregate and per-channel PCM level fields (`peak_dbfs`, `rms_dbfs`, and `crest_factor`) without implying LUFS or true-peak analysis.

The underlying snapshot, rollback, semantic diff, automation validation, and audio inspection behavior is unchanged from 1.0.2.

Validation: `python -m compileall -q src`, `python -m pytest -q -p no:cacheprovider` (4 passed), and `uv build` (1.0.3 sdist and wheel).
