# Changelog

All notable changes to VPN Exit Bench are documented here.

The project is under active development and does not yet promise semantic-version compatibility for every internal API or score model.

## Unreleased

### Security / public-release hardening

- added MIT license
- added security, privacy and contribution policies
- added runtime VPN-config validation in addition to upload validation
- added optional HTTP Basic Authentication
- added CSRF protection for state-changing API requests
- removed `unsafe-inline` from script execution with per-response CSP nonces; dynamic style attributes remain narrowly allowed for the existing UI
- documented and supported Docker Socket Proxy deployments through `DOCKER_HOST`
- reduced benchmark-worker capabilities to the networking capabilities required by the tests
- added `no-new-privileges` and a worker PID limit
- added Dependabot configuration
- added CodeQL analysis
- added dependency-review workflow
- added Python dependency/static-analysis and Trivy filesystem/container scans
- pinned GitHub Actions to full commit SHAs
- pinned the Python base image to a specific Python/Alpine version
- enabled Docker build SBOM/provenance metadata

### Privacy

- pre-VPN public IP is no longer persisted or returned through job results
- older local result payloads are scrubbed on application startup
- Docker/Git ignore rules cover common VPN key/config formats

### Benchmark / UI

- separated Raw Speed from EU Peer Connectivity
- peer measurements cover NL, DE, CH, DK, SE, PL and RO
- weighted EU Peer Score with a worst-route penalty
- interactive Europe peering map grouped by provider/config
- country-by-country peer matrix
- benchmark comparison sections sort best-to-worst per metric
- config/result lists become internally scrollable after five rows
- added **Smart** benchmark mode as the default for substantially shorter multi-config runs
- Smart mode prechecks Frankfurt/Amsterdam and performs the full raw-speed test only against the better reachable reference target
- Smart mode uses shorter iPerf windows, fewer ICMP samples and fewer failed-port retries while retaining all seven EU peer regions and port-forwarding checks
- failed regional iPerf probes fall back to the secondary datacenter endpoint when available
- harmless ping/precheck probes run in parallel while throughput measurements remain serial to avoid self-induced bandwidth contention
- added selectable **Deep** mode that retains the previous long FRA + AMS raw-speed measurements and longer sample windows
- added benchmark **Pause / Resume / Cancel** controls to the live progress panel
- pausing lets the current config finish cleanly, then stops before the next config so iPerf measurements are not corrupted
- cancelling stops the current worker immediately, discards the partial current-config result and keeps already completed results

## 2026-09-01

- initial Unraid-native VPN Exit Bench implementation
- WireGuard/OpenVPN worker isolation
- direct-line baseline
- qBittorrent-oriented torrent score
- Proton NAT-PMP port-forwarding checks
- initial GHCR image and Unraid XML template
