# FL CLI independent blind acceptance

Original raw evidence root: `.lab/blind-acceptance/run-20261026T103909Z-fa584177/`. Evidence paths below are relative to that root.

**PASSED** on frozen HEAD `44d606591c54240dcdd1cb7a53e3dabb235c390c`, installed FL Studio **26.1.6.5639**.

Two independently written tasks were committed before the first CLI build: different tempos, five and three voices, non-default Pattern numbers, deliberately different key/time/length/velocity records, shuffled channel/Mixer order and explicit repeated Playlist clips. Samples are finite, independently generated sine WAVs. The developer received only failure categories during repairs and did not read the hidden requests. Only README, quickstart and CLI usage were consulted; implementation, tests, developer demos and old MCP were not read or run.

| Final native output | Duration | Note activity/frequency | Isolated onsets | Planned silence |
|---|---:|---:|---:|---:|
| a-original | 10.816440 s | 20/20 | 5/5 | 5/5 |
| a-revised | 10.816440 s | 23/23 | 5/5 | 5/5 |
| b-original | 8.892744 s | 17/17 | 6/6 | 2/2 |
| b-mixed | 8.892744 s | 16/16 | 6/6 | 2/2 |

All **76/76** planned note activity and frequency windows, **22/22** isolated onset anchors and **14/14** planned silence windows pass in independently decoded actual FL PCM. Frequency peaks and expected-frequency energy were measured from the generated samples and requested keys, at the predeclared tempo/Playlist times. File existence, return counts and whole-file RMS alone were insufficient acceptance evidence.

Each saved score exactly matches key/start/length/velocity. Replacing one score preserves all complete records in the other four voices; their native PCM bar regions are also identical. Original source FLP hashes remain unchanged. The second task combines score/channel/Mixer/effect changes and renders the correct voice content. A final dry-run leaves the entire blind run tree SHA-256 map unchanged; repeat output is rejected without changing its FLP.

The prior c1368d9 pass is preserved as `report-before-pan.md/json`, with all 109 sealed files hash-verified unchanged. A further observation of zero right-channel dry PCM paused delivery; the developer independently corrected channel-pan storage, and the same original four outputs were regenerated at this final freeze. In the observed B dry window, original L/R RMS is 0.186703379/0.186703379; the requested left edit gives 0.248396864/0.139171938. This updates the actual stereo observation without adding tasks, changing the original acceptance thresholds or certifying arbitrary pan-law precision.

**Comparison:** the final CLI is better on these observed independent tasks than the user's historical old-MCP failure in target assignment, persistent actual files, evidence-backed success and automatic JSON-to-FLP-to-native-render completion. The historical baseline was 71 intended notes collapsing to one roll, optimistic success without score readback, a GUI hang/data loss, and later MIDI plus manual import. The unsafe chain was never rerun. This is a functional historical comparison, not a matched-input simultaneous double-blind A/B or an aesthetic ranking.

The first attempts did fail. Their raw evidence is preserved: (1) whole-project silent export despite success, (2) silent replacement voice despite correct parsed records, (3) combined edit still incomplete, and (4) effect-scope energy in a planned early silence interval. The same inputs and unchanged thresholds were used throughout. After each real failure only the necessary affected path was rechecked; the final freeze regenerated all four outputs.

Scope is factory Basic sampler projects, explicit pattern clips and one installed factory effect. Arbitrary Automation, edited variable-length clips, third-party custom UI and unsaved-memory attachment were not evaluated. Exact arbitrary effect-tail duration was not a requirement. No user editor GUI was operated, and no production code or test framework was changed by this tester.

Evidence paths and exact command/result logs are listed in `report.json`. Four final FLPs/WAVs and independent per-note audio measurements are in `final-20261026T112128Z/`; all prior failure artifacts remain alongside their round reports. The input-integrity sidecar distinguishes canonical LF task-spec hashes from Windows CRLF bytes; raw bytes match the pre-build snapshot.

Final four-output workflow: 17.610 s; summed final CLI command time including the two bounded checks: 16.876 s. Total elapsed including independent developer repair waits: 2606.2 s.

