# FL Studio CLI 1.0.2

This patch synchronizes the runtime version reported by `flstudio_cli.__version__` with the package metadata and the published fullstack release line. The 1.0.1 feature set remains unchanged: bounded project snapshots with reusable deltas, readback-aware live rollback, semantic Playlist diffing, safer automation validation, and per-channel audio dBFS metrics.

Validation:

```text
python -m compileall -q src
python -m pytest -q -p no:cacheprovider   # 4 passed
uv build                                     # 1.0.2 sdist and wheel
```
