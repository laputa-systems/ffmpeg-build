# Roadmap

This is the single plan for this repository: all current and future work, and the handoff for resuming it. Campaigns are sections below, and their items interleave in **Sequence**. "Resume the roadmap" means continue from **Status**.

## Status

- **State:** idle; no campaign or slice is in progress.
- **Last accepted:** extraction S0–S12; producer release `20261104`, Player `v0.42.1`, and the `usr` FFmpeg pair were recorded as accepted. The plan did not identify a last accepted integration revision or green status.
- **Parked branches:** none recorded.
- **Next slice:** none planned; see Later for open work.
- **Resume:** say “resume the roadmap” or “resume the campaign”.

## Sequence

No slices are ready.

## Later

- FFB-6: Decide whether tools supports toolbox workflows and provide the required components or document the non-consumer decision; see [the ticket](../TODO.md).
- FFB-1: Support Discover's WebP thumbnail encoding in tools and runtime; see [the ticket](../TODO.md).
- FFB-2: Evaluate a Chromium-compatible shared FFmpeg profile; see [the ticket](../TODO.md).
- FFB-3: Establish representative shipped media throughput baselines; see [the ticket](../TODO.md).
- FFB-4: Establish repeatable native profile build-cost baselines; see [the ticket](../TODO.md) and [baseline evidence](baseline.md).
- FFB-5: Measure shipped artifact sizes and startup; see [the ticket](../TODO.md).
- Qualify Apple VideoToolbox with `encode archive-720p-cq52 <disposable fixture>` and confirm HEVC `hvc1` and AAC output; encoder availability alone does not prove hardware execution. No ticket recorded.
- Qualify provisioning on a disposable Alpine edge host with `doas env INSTALL_MODE=server sh usr/host/alpine/install.sh` and `doas sh usr/host/alpine/verify.sh`; container tests do not prove host provisioning. No ticket recorded.
- Qualify real GPU VA-API decode with `tests/run.sh linux-vaapi`, a `/dev/dri/renderD*` node, and a VA driver; SDK linkage audit alone does not prove hardware decode. No ticket recorded.
- Run Player's GUI, audio, and visual checks on the owner's machine with `scripts/manual-checklist.sh --fixture-dir .work/fixtures --release`. No ticket recorded.
- Verify whether the previously recorded local `usr` FFmpeg-pair commits still need to be pushed; the extraction status recorded that as an owner action. No ticket recorded.
- Follow up the buildlib bootstrap mutation-selector coverage and possible downloader removal; see [buildlib adoption](buildlib-adoption.md#follow-up-outside-this-slice). No ticket recorded.
