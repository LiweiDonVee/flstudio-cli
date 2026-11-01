# FL Studio CLI1.2.1

New Automation Clips no longer inherit an existing Automation Clip's mute flag.
Only the new record is activated; existing clips, other flags, opaque tails,
track enable states and arrangement selection are retained.

The Agent references now explain source-clip versus song timing, the need to
identify the channel actually playing a multisample phrase, and analysis-window
selection for rapid pitch movements. See [automation timing](automation-timing.md).

Verification on Windows x64, Python3.12, FL Studio Producer26.1.6.5639:

- Ten concise regression checks passed. The new single check covers both old
  clip mute states, saved readback and byte preservation of existing records.
- Real-engine full-project pitch controls were checked with constant0.5/0.45
  curves (approximately−480cents), and with the unchanged dense expression
  curves (approximately−240cents at two phrase endings). These diagnose the
  pitch path; they are not new plugin-coverage or listening-quality claims.
- Fast glides can be rejected as low-periodicity in a50ms pitch window. A20ms
  window with a known200Hz lower bound recovered the demonstrated550–800Hz
  motion while retaining the0.90 threshold and unknown frames.

The1.2.0 Producer/plugin scope is unchanged. Its
[five WAV previews and recoverable32-case bundle](https://github.com/LiweiDonVee/flstudio-cli/releases/tag/v1.2.0)
remain available. This patch does not redistribute private diagnostic songs or
FL/plugin factory files.

Assets: installable wheel, updated Agent Skills, automation timing reference
andSHA256SUMS. Install the wheel with the `sound-design` extra for NumPy analysis.
Existing editable installs can update their checkout without rebuilding their
tool environment while another Agent is using it.
