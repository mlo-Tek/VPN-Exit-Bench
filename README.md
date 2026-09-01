# VPN Exit Bench for Unraid

VPN Exit Bench is built for **Unraid's native Docker/Community Applications workflow**. It does **not require Docker Compose**.

The app benchmarks WireGuard (`.conf`) and OpenVPN (`.ovpn`) exit configs one by one in isolated short-lived Docker worker containers, so the Unraid host route itself is not changed.

## What it measures

- public IP before/after VPN
- exit IP/city/country/provider when available
- ICMP latency
- packet loss
- jitter
- DNS lookup time
- HTTP download throughput

## Unraid installation

The Docker image is published automatically to:

`ghcr.io/mlo-tek/vpn-exit-bench:latest`

The Unraid Docker XML template is:

`https://raw.githubusercontent.com/mlo-Tek/VPN-Exit-Bench/main/unraid/vpn-exit-bench.xml`

Use the XML as a normal Unraid Docker template. The default persistent appdata path is:

`/mnt/cache/appdata/vpn-exit-bench`

The Web UI uses port `8787`.

## VPN config folders

Create provider folders below:

`/mnt/cache/appdata/vpn-exit-bench/vpns/`

For example:

```text
/mnt/cache/appdata/vpn-exit-bench/vpns/Proton/DE-Frankfurt-01.conf
/mnt/cache/appdata/vpn-exit-bench/vpns/Proton/NL-Amsterdam-01.conf
/mnt/cache/appdata/vpn-exit-bench/vpns/OVPN/DE-Frankfurt.ovpn
/mnt/cache/appdata/vpn-exit-bench/vpns/OVPN/NL-Amsterdam.ovpn
```

The first folder level becomes the provider name in the UI.

## Required Unraid mappings

The XML template configures these automatically:

- Web UI: container port `8787`
- Appdata: `/mnt/cache/appdata/vpn-exit-bench` -> `/config`
- Docker socket: `/var/run/docker.sock` -> `/var/run/docker.sock`
- `WORKER_IMAGE=ghcr.io/mlo-tek/vpn-exit-bench:latest`
- `HOST_CONFIG_DIR=/mnt/cache/appdata/vpn-exit-bench/vpns`
- `DOWNLOAD_MB=100`

The Docker socket is required because the web container starts a separate test worker for each VPN location. Each worker gets only `NET_ADMIN` and `/dev/net/tun`; the Unraid host route is not modified.

## OpenVPN note

If an `.ovpn` file references external files such as `auth-user-pass`, `ca`, `cert`, or `key`, those files must currently be embedded into the `.ovpn` file. WireGuard `.conf` files work directly.

## Project

GitHub: https://github.com/mlo-Tek/VPN-Exit-Bench
