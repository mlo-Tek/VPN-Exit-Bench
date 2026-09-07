# Changelog

## Unreleased

- Torrent Score is now port-neutral: port-forwarding status remains visible but no longer changes the recommendation score.
- Torrent Score weighting now focuses on EU Peer Connectivity (50%), Raw Speed (40%) and Stability/Latency (10%).
- Suspicious iPerf results below 20 Mbps are automatically rechecked twice and replaced by the median of three successful samples, preventing a single transient 1–2 Mbps result from ruining a VPN exit ranking while preserving genuinely slow routes.
- Benchmark payload version increased to 4 for the new measurement behavior.

## 2026-09-02

- Hardened the public release and added Smart/Deep benchmark modes.
- Added benchmark pause/resume/cancel controls.
