# VPN Exit Bench for Unraid

> [!WARNING]
> ## ⚠️ VIBE-CODED PROJECT
> **VPN Exit Bench was built primarily through AI-assisted / vibe coding.**
>
> The project is actively tested and reviewed, but it has **not** undergone a professional third-party security audit. Review the code before trusting it in a sensitive environment and **do not expose the WebUI directly to the public internet**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

VPN Exit Bench is an **Unraid-native** tool for comparing WireGuard (`.conf`) and OpenVPN (`.ovpn`) VPN exit points for qBittorrent / torrent usage.

It is designed for **Unraid's normal Docker / Community Applications workflow**. **Docker Compose is not required or used.**

Each VPN config is benchmarked in its own short-lived Docker worker so the Unraid host route itself is not changed.

---

## What the project tries to answer

VPN Exit Bench separates two different questions:

1. **How fast is this VPN exit?**
   - raw download capacity
   - raw upload capacity
   - single-stream performance
   - latency, jitter and packet loss

2. **How well does this VPN exit reach typical European seedbox / peer regions?**
   - Netherlands
   - Germany
   - Switzerland
   - Denmark
   - Sweden
   - Poland
   - Romania

The peer test is a **peering/connectivity proxy** using public datacenter endpoints. It does not connect to private tracker peers and cannot know where every real seeder is located.

---

## Main features

- WireGuard and OpenVPN support
- upload/manage configs directly from the WebUI
- sequential isolated benchmark workers
- direct internet baseline
- Raw Speed Score
- EU Peer Connectivity Score
- qBittorrent-oriented Torrent Score
- Proton NAT-PMP port-forwarding test
- manual forwarded-port support for providers such as OVPN
- live benchmark progress
- persistent local result history
- multi-config comparisons
- automatic best-to-worst sorting per metric
- interactive Europe peering map per provider/config
- country-by-country peer matrix
- internally scrollable config/result lists after five rows
- runtime rejection of executable VPN config hooks
- CSRF protection
- optional HTTP Basic Authentication
- restricted Docker Socket Proxy deployment support

---

## Benchmark model

### Raw Speed

Raw capacity uses fixed references so every exit is measured against the same paths.

Current references:

- Leaseweb Frankfurt
- Leaseweb Amsterdam

Measurements include:

- single-stream download
- multi-stream download
- multi-stream upload
- ICMP latency
- jitter
- packet loss
- DNS lookup timing

### EU Peer Connectivity

Short iPerf3 and ICMP probes are made toward public datacenter/network endpoints in:

| Region | Weight in EU Peer Score |
|---|---:|
| Netherlands | 25% |
| Germany | 25% |
| Switzerland | 20% |
| Denmark | 10% |
| Sweden | 10% |
| Poland | 5% |
| Romania | 5% |

Within each region, upload is weighted more heavily than download because upload quality matters strongly for seeding. A weak route is also penalized so one exceptional route cannot completely hide poor connectivity toward the rest of Europe.

### Torrent Score

Current overall weighting:

| Component | Weight |
|---|---:|
| EU Peer Connectivity | 45% |
| Raw Speed | 25% |
| Incoming Port / Port Forwarding | 20% |
| General Stability / Latency | 10% |

The UI keeps these concepts separate:

- **Speed Score** — raw VPN capacity
- **EU Peer Score** — European datacenter/seedbox connectivity
- **Torrent Score** — combined qBittorrent-oriented recommendation

---

## Europe peering map

The comparison view contains a Europe connectivity map for every selected **VPN provider + config**.

- green / stronger lines = better measured route
- yellow = medium
- red = weaker route
- country nodes show regional connectivity scores

Provider tabs keep Proton, OVPN and other providers separate. Config tabs switch individual exits. The matrix next to the map highlights the best config of that provider for each destination region.

---

# Unraid installation

Docker image:

```text
ghcr.io/mlo-tek/vpn-exit-bench:latest
```

Unraid XML template:

```text
https://raw.githubusercontent.com/mlo-Tek/VPN-Exit-Bench/main/unraid/vpn-exit-bench.xml
```

Default appdata:

```text
/mnt/cache/appdata/vpn-exit-bench
```

Default WebUI:

```text
http://UNRAID-IP:8787
```

> [!IMPORTANT]
> Keep port `8787` on a trusted LAN/management network. Do not directly port-forward it and do not treat the application as an internet-facing service.

---

## Authentication

The Unraid template exposes optional:

- `AUTH_USERNAME`
- `AUTH_PASSWORD`

Set **both** to enable HTTP Basic Authentication. If both are empty, authentication is disabled for backwards compatibility.

When enabled, the browser shows its normal HTTP authentication prompt. Use a strong unique password.

> [!CAUTION]
> HTTP Basic Authentication is **authentication, not encryption**. Over plain `http://` the credentials are only Base64-encoded and can be read by anyone able to intercept that connection. Use it only on a trusted LAN, or terminate HTTPS at a trusted local reverse proxy/TLS endpoint. This still does **not** make direct public internet exposure recommended.

CSRF protection for state-changing API requests is enabled regardless of whether Basic Authentication is configured.

Authentication reduces accidental/LAN access risk, but **does not make direct public internet exposure recommended**, especially because the application can create Docker containers.

---

# Recommended Docker access: Socket Proxy

The main security-sensitive part of VPN Exit Bench is Docker API access. Direct access to `/var/run/docker.sock` is effectively privileged host access if the application were ever compromised.

For new installations, the recommended layout is:

```text
Browser/LAN
   │
   ▼
VPN Exit Bench
   │  restricted Docker HTTP API
   ▼
vpn-exit-bench-socket-proxy
   │
   ▼
/var/run/docker.sock
```

Only the dedicated proxy container receives the real Docker socket. Its TCP port is kept on a private Docker network and is **not published to the LAN**.

### One-time private Docker network

Unraid does not need Docker Compose. Create one private user-defined bridge network once from the Unraid terminal:

```bash
docker network create vpn-exit-bench
```

### Install the Socket Proxy

Proxy XML template:

```text
https://raw.githubusercontent.com/mlo-Tek/VPN-Exit-Bench/main/unraid/vpn-exit-bench-socket-proxy.xml
```

The template uses `tecnativa/docker-socket-proxy:v0.5.0` and enables only the Docker API area/actions required to inspect, create, start, stop/kill and remove benchmark workers.

The proxy intentionally publishes **no host port**.

### Configure VPN Exit Bench for proxy mode

In the VPN Exit Bench Unraid template:

1. change **Network Type** to the custom `vpn-exit-bench` network;
2. set:

```text
DOCKER_HOST=tcp://vpn-exit-bench-socket-proxy:2375
```

3. remove the main container's `/var/run/docker.sock` mapping;
4. keep the proxy and VPN Exit Bench on the same private `vpn-exit-bench` network.

The benchmark workers themselves are still created on Docker's normal bridge network so they can reach the internet through their test VPN.

### Legacy/direct mode

Existing installations can continue using:

```text
/var/run/docker.sock -> /var/run/docker.sock
```

This remains supported for compatibility but carries a larger host-impact risk than the proxy layout.

---

## Worker isolation

Each benchmark runs in a temporary worker container.

The worker:

- does **not** receive the Docker socket
- receives only the selected VPN config as a read-only mount
- drops the normal Docker capability set
- receives only `NET_ADMIN`, `NET_RAW` and `NET_BIND_SERVICE`
- uses `no-new-privileges`
- has a PID limit
- receives `/dev/net/tun`
- is deleted after the benchmark

This is isolation, not a formal sandbox guarantee.

---

## VPN config storage

Configs are stored below:

```text
/mnt/cache/appdata/vpn-exit-bench/vpns/
```

Example:

```text
/mnt/cache/appdata/vpn-exit-bench/vpns/Proton/proton-de.conf
/mnt/cache/appdata/vpn-exit-bench/vpns/Proton/proton-nl.conf
/mnt/cache/appdata/vpn-exit-bench/vpns/OVPN/ovpn-ch.conf
```

The first directory level becomes the provider name in the UI.

Uploaded files are written with restrictive permissions where supported.

> [!CAUTION]
> WireGuard and OpenVPN configs frequently contain **private keys, certificates or credentials**. Never commit real VPN configs to GitHub and do not share them publicly.

---

## VPN config execution protection

VPN configuration formats can contain directives that execute programs.

VPN Exit Bench rejects unnecessary executable/control hooks such as WireGuard `PreUp`, `PostUp`, `PreDown`, `PostDown` and OpenVPN script/plugin/management directives.

Validation happens in two places:

1. when a config is uploaded through the WebUI;
2. **again inside the worker immediately before the config is executed**.

The second check is important because it also protects configs copied manually into the appdata directory.

---

# Security and privacy

## Public IP handling

The worker temporarily determines the direct public IP to verify that the VPN changed the egress route.

Current versions:

- do not persist the pre-VPN public IP
- do not return it through job results
- scrub it from older local result payloads at startup
- do not persist a direct baseline public IP

VPN **exit IPs** remain in local benchmark results because they identify the exits being compared.

See [PRIVACY.md](PRIVACY.md) for the full data-flow description.

## External benchmark services

Tests intentionally contact external services, including public-IP lookup services, Cloudflare/Google ICMP targets, Leaseweb speed-test endpoints, European public iPerf3/datacenter targets and an external port checker.

These services naturally see the source IP used for the request. During a direct baseline that source is the user's normal internet address; during VPN measurements it should normally be the VPN exit.

## Browser security

The WebUI uses:

- CSRF protection for mutating requests
- `X-Content-Type-Options: nosniff`
- frame blocking
- no-referrer policy
- restricted browser permissions
- Content Security Policy with nonce-protected script execution
- no-store API responses

Dynamic UI styling still requires inline **style attributes**; script execution does not rely on `unsafe-inline`.

## Secret/build hygiene

`.gitignore` and `.dockerignore` cover common sensitive material, including:

- `*.conf`
- `*.ovpn`
- `*.key`
- `*.pem`
- `*.p12` / `*.pfx`
- `.env*`
- `results.db`
- local `vpns/` and `config/` directories

The published Docker build therefore does not intentionally include local VPN configs or appdata.

---

# Automated security checks

The public repository includes:

- **CodeQL** Python analysis
- **pip-audit** dependency vulnerability checks
- **Bandit** high-severity Python static checks
- **Trivy** repository vulnerability/secret/misconfiguration scanning
- **Trivy** built-container vulnerability/secret scanning
- **Dependency Review** on pull requests
- **Dependabot** for Python, Docker and GitHub Actions
- GitHub Actions pinned to full commit SHAs
- GHCR image SBOM/provenance metadata

Security automation reduces risk but does not replace code review or an independent audit.

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

---

## Security review status

A source-level review of the public `main` tree was performed during the 2026-09-02 hardening work.

At that time no real WireGuard/OpenVPN configs, WireGuard private-key fields, PEM private-key blocks or user-specific Unraid/VLAN addresses were found in the current repository tree.

This statement applies to the reviewed current tree and is **not a forensic guarantee about every historical commit**. If a real credential is ever committed, deleting it later is not sufficient: it must be revoked/rotated.

---

## OpenVPN note

If an `.ovpn` file references separate local CA/certificate/key files, those files are not automatically mounted into the worker. Provider configs work best when required certificates/keys are embedded in the `.ovpn` file itself.

Executable OpenVPN script/plugin/management hooks are intentionally unsupported.

---

## Data persistence

Persistent data lives under `/config`, normally backed by:

```text
/mnt/cache/appdata/vpn-exit-bench
```

This includes uploaded VPN configs and `results.db`. Recreating the Docker container does not remove these files as long as the appdata mapping remains intact.

---

# Contributing and project policy

- Contributions: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security reports: [SECURITY.md](SECURITY.md)
- Privacy: [PRIVACY.md](PRIVACY.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- License: [MIT](LICENSE)

The project is under active development. Benchmark endpoints and scoring can change as more real-world measurements are collected.

## License

VPN Exit Bench is released under the **MIT License**. See [LICENSE](LICENSE).

GitHub: https://github.com/mlo-Tek/VPN-Exit-Bench
