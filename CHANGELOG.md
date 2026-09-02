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
- removed `unsafe-inline` from the Content Security Policy by using per-response nonces
- documented and supported Docker Socket Proxy deployments through `DOCKER_HOST`
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

## 2026-09-01

- initial Unraid-native VPN Exit Bench implementation
- WireGuard/OpenVPN worker isolation
- direct-line baseline
- qBittorrent-oriented torrent score
- Proton NAT-PMP port-forwarding checks
- initial GHCR image and Unraid XML template
