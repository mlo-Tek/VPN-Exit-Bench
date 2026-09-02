# VPN Exit Bench for Unraid

> [!WARNING]
> ## ⚠️ VIBE-CODED PROJECT
> **VPN Exit Bench was built primarily through AI-assisted / vibe coding.**
>
> The project is actively tested and reviewed, but it has **not** undergone a professional third-party security audit. Review the code yourself before trusting it in a sensitive environment, and **do not expose the WebUI directly to the public internet**.

VPN Exit Bench is an **Unraid-native** tool for comparing WireGuard (`.conf`) and OpenVPN (`.ovpn`) VPN exit points for qBittorrent / torrent usage.

It is designed for **Unraid's normal Docker / Community Applications workflow**. **Docker Compose is not required or used.**

Each VPN config is benchmarked in its own short-lived isolated Docker worker. The Unraid host route itself is not changed.

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

The second part is intended as a **peering / connectivity proxy**. It does not connect to private tracker peers and cannot know where every real seeder is located.

---

## Main features

- WireGuard and OpenVPN support
- VPN configs can be uploaded directly from the WebUI
- multiple configs can be selected, tested and deleted
- Proton port forwarding tested automatically through NAT-PMP
- manual forwarded qBittorrent port support for providers such as OVPN
- direct internet connection can be measured as a baseline
- sequential benchmark execution so VPN tests do not compete for bandwidth
- live benchmark progress with individual measurement phases
- persistent benchmark history
- multi-config result comparison
- automatic best-to-worst sorting per metric
- raw speed comparison charts
- EU peer-connectivity scoring
- interactive Europe peering map per VPN provider and config
- country-by-country comparison matrix
- configurable result/config lists with internal scrolling instead of endlessly growing pages

---

## Benchmark model

### Raw Speed

Raw capacity is measured against fixed reference endpoints so every VPN exit is tested against the same paths.

Current primary raw-speed references:

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

Short iPerf3 and ICMP probes are made toward public datacenter / network endpoints in:

| Region | Weight in EU Peer Score |
|---|---:|
| Netherlands | 25% |
| Germany | 25% |
| Switzerland | 20% |
| Denmark | 10% |
| Sweden | 10% |
| Poland | 5% |
| Romania | 5% |

Within each region, upload is weighted more heavily than download because upload quality matters strongly for seeding.

A weak route is also penalized so one extremely good Amsterdam path cannot completely hide poor connectivity toward the rest of Europe.

### Torrent Score

Current overall weighting:

| Component | Weight |
|---|---:|
| EU Peer Connectivity | 45% |
| Raw Speed | 25% |
| Incoming Port / Port Forwarding | 20% |
| General Stability / Latency | 10% |

The UI therefore keeps these scores separate:

- **Speed Score** — raw VPN capacity
- **EU Peer Score** — connectivity toward European datacenter/seedbox regions
- **Torrent Score** — combined qBittorrent-oriented recommendation

---

## Europe peering map

The comparison view contains a Europe connectivity map.

For every selected **VPN provider + config** it shows routes from that exit toward the measured peer regions.

- green / stronger lines = better measured route
- yellow = medium
- red = weaker route
- country nodes show their regional connectivity score

Provider tabs keep Proton, OVPN and other providers separate. Config tabs let you switch between individual exit points of the same provider.

The matrix next to the map highlights which config of that provider currently performs best for each destination region.

---

## Unraid installation

The Docker image is published to:

```text
ghcr.io/mlo-tek/vpn-exit-bench:latest
```

The Unraid XML template is:

```text
https://raw.githubusercontent.com/mlo-Tek/VPN-Exit-Bench/main/unraid/vpn-exit-bench.xml
```

Use the XML as a normal Unraid Docker template.

Default persistent appdata path:

```text
/mnt/cache/appdata/vpn-exit-bench
```

WebUI:

```text
http://UNRAID-IP:8787
```

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

Uploaded config files are written with restrictive file permissions where supported.

> [!CAUTION]
> WireGuard and OpenVPN configs frequently contain **private keys, certificates or credentials**. Never commit your own VPN configs to GitHub and do not share them publicly.

---

## Required Unraid mappings

The XML template configures:

- WebUI port `8787`
- `/mnt/cache/appdata/vpn-exit-bench` → `/config`
- `/var/run/docker.sock` → `/var/run/docker.sock`
- `WORKER_IMAGE=ghcr.io/mlo-tek/vpn-exit-bench:latest`
- host VPN config directory

The Docker socket is required because the WebUI container creates short-lived VPN benchmark workers.

Workers are started with:

- `NET_ADMIN`
- `/dev/net/tun`
- only the selected VPN config mounted read-only

The worker does **not** receive the Docker socket.

---

## Security and privacy

### Important: Docker socket access

The main container currently needs **read/write access to `/var/run/docker.sock`**.

That is security-sensitive. Access to the Docker daemon is effectively highly privileged access to the Unraid host. A remote-code-execution vulnerability in the WebUI container could therefore have serious host impact.

For that reason:

- keep the WebUI on a trusted LAN / management VLAN
- do not port-forward port `8787`
- do not expose it directly through a public reverse proxy
- do not treat the application as an internet-facing service

### Authentication

VPN Exit Bench currently has **no built-in user authentication**.

Anyone who can reach the WebUI/API can start benchmarks and manage uploaded configs/results. Network-level access control is therefore important.

### VPN config protection

The repository ignores common local config/database paths through `.gitignore` and `.dockerignore`.

The Docker build context explicitly excludes common sensitive VPN material such as:

- `*.conf`
- `*.ovpn`
- `*.key`
- `*.pem`
- local `vpns/` and `config/` folders
- `.env`
- `results.db`

Uploaded configs are checked for dangerous WireGuard/OpenVPN script-hook directives before being accepted by the WebUI.

### Public IP handling

The benchmark needs to determine the direct public IP temporarily in memory so it can verify that a VPN tunnel actually changed the egress address.

Current versions do **not persist the pre-VPN public IP** in benchmark results. Older locally stored results are scrubbed on application startup.

VPN **exit IPs** remain part of the local benchmark result because they are useful for identifying and comparing exit nodes.

Benchmark data stays in the local appdata database unless you explicitly copy/share it elsewhere.

### External services contacted

Depending on the benchmark phase, the worker communicates with services such as:

- IP information / public-IP lookup services
- Cloudflare / Google ICMP targets
- Leaseweb speed-test endpoints
- public European iPerf3 endpoints used for peer-connectivity measurements
- the external port checker used for incoming-port verification

These remote services can naturally see the source IP used for that particular request. During VPN measurements this should normally be the VPN exit IP; during a direct baseline test it is the direct internet connection.

---

## Security review status

A source-level review of the current `main` branch was performed on **2026-09-02**.

At that time:

- no WireGuard/OpenVPN config files were committed in the current repository tree
- no WireGuard `PrivateKey` / `PresharedKey` values were found
- no PEM/private-key blocks were found
- no user-specific Unraid/VLAN addresses were found in the repository
- GitHub Actions uses the normal `${{ secrets.GITHUB_TOKEN }}` reference; the token value itself is not stored in the repository
- hard-coded IP addresses that do exist in the source are public benchmark targets or the documented Proton NAT-PMP gateway, not the maintainer's home/server addresses

This is **not a guarantee that the project is vulnerability-free** and is not a substitute for an independent security audit.

---

## OpenVPN note

If an `.ovpn` file references separate local files such as CA/certificate/key files, those files are not automatically mounted into the worker.

Provider configs work best when the required certificates/keys are embedded in the `.ovpn` file itself.

Configs containing executable OpenVPN script/plugin hooks are intentionally rejected by the WebUI for security reasons.

---

## Data persistence

Persistent data lives under `/config`, normally backed by:

```text
/mnt/cache/appdata/vpn-exit-bench
```

This includes:

- uploaded VPN configs
- `results.db`
- benchmark history / baseline data

Deleting and recreating the Docker container does not remove these files as long as the appdata mapping remains intact.

---

## Project status

This project is under active development and the scoring model may continue to change as more real-world VPN/seedbox measurements are collected.

GitHub: https://github.com/mlo-Tek/VPN-Exit-Bench
