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
- Torrent Score is port-neutral: port-forwarding status remains visible but no longer changes the recommendation score
- Torrent Score weighting focuses on EU Peer Connectivity (50%), Raw Speed (40%) and Stability/Latency (10%)
- iPerf throughput now uses receiver-confirmed `sum_received` for upload and download; sender-side values remain diagnostic only, preventing short parallel upload tests from reporting buffered rates above the real WAN uplink
- iPerf results without receiver-confirmed bitrate are rejected instead of falling back to potentially inflated sender-side throughput
- suspicious successful iPerf measurements below 20 Mbps are automatically rechecked twice and evaluated using the median of three successful samples
- persistent genuinely slow paths remain slow after the median check; a single transient 1–2 Mbps sample can no longer ruin a ranking by itself
- benchmark payload version increased to 4 for the robust iPerf measurement behavior
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
- benchmark runs are now additive: new manual or batch tests no longer hide results from configs that were not retested
- the results view shows the newest run per provider/config while retaining older runs in SQLite as history
- `/api/results?history=1` exposes the complete stored benchmark history, while the default results endpoint remains focused on the latest run per config
- current result entries include `history_count` so repeated measurements can be identified without deleting prior runs
- exit metadata now includes ASN, network organization, canonical ISP/hoster, BGP prefix and reverse DNS without affecting the benchmark score
- the ISP/hoster catalog includes the CryptoStorm networks observed in real configs (M247, UNITED COLO, NForce Entertainment, AltusHost and Private Layer) plus common VPN/datacenter networks such as DataCamp/CDN77, DataPacket, Leaseweb, Worldstream, Clouvider, Serverius, NovoServe, Hetzner, OVHcloud, Vultr, DigitalOcean, Gcore, Hivelocity and others
- the results view now shows a compact exit-network profile per run and an aggregated ASN/ISP overview, e.g. `AS9009 · M247 · 2 Exits`
- ISP/ASN metadata is informational only; Torrent Score weighting and port-neutral scoring remain unchanged
- CryptoStorm configs using the short `cs-*.conf` naming convention are now recognized as **CryptoStorm** even when they physically remain in the legacy `Other/` directory
- manual qBit ports are shared as a provider default across otherwise empty configs of the same VPN provider, while explicit per-config overrides remain intact
- a successfully completed benchmark with a manually supplied qBit port can no longer fall back to `Unbekannt`: the server preserves the requested port and reports it at least as configured/unverified when external reachability cannot be proven
- manually supplied forwarded ports are no longer reported as definitely `closed` solely because a probe against the current VPN exit IP fails
- manual port-forward checks now distinguish `open` from `mapped_unverified`; a negative exit-IP probe is retained as diagnostic metadata because some VPN providers expose forwarding through a different ingress IP than the public exit IP
- the worker records whether the current exit-IP probe completed and whether it accepted TCP while keeping provider-side forwarding status explicitly unverified unless external reachability is positively confirmed

## 2026-09-01

- initial Unraid-native VPN Exit Bench implementation
- WireGuard/OpenVPN worker isolation
- direct-line baseline
- qBittorrent-oriented torrent score
- Proton NAT-PMP port-forwarding checks
- initial GHCR image and Unraid XML template
