# VPN Exit Bench for Unraid

Web UI to benchmark WireGuard (`.conf`) and OpenVPN (`.ovpn`) exit configs one by one in isolated Docker containers.

## What it measures
- public IP before/after VPN
- exit IP/city/country/provider when ipinfo.io returns metadata
- ICMP latency (8 probes to 1.1.1.1)
- packet loss
- basic jitter
- DNS lookup time
- HTTP download throughput through Cloudflare's speed endpoint

## Unraid paths
Create folders such as:

```
/mnt/cache/appdata/vpn-exit-bench/vpns/Proton/
/mnt/cache/appdata/vpn-exit-bench/vpns/OVPN/
/mnt/cache/appdata/vpn-exit-bench/vpns/Mullvad/
```

Put configs in them, e.g.:

```
Proton/DE-Frankfurt-01.conf
Proton/NL-Amsterdam-01.conf
OVPN/DE-Frankfurt.ovpn
OVPN/NL-Amsterdam.ovpn
```

The first folder level is shown as the provider name.

## Build/start on Unraid

```bash
cd /mnt/cache/appdata/vpn-exit-bench-src
docker compose build
docker compose up -d
```

Then open:

```
http://UNRAID-IP:8787
```

## Important
The web container mounts `/var/run/docker.sock` because it creates short-lived worker containers. Each worker gets only `NET_ADMIN` + `/dev/net/tun`; the Unraid host route itself is not altered.

If an OpenVPN config references external files (`auth-user-pass`, `ca`, `cert`, `key`), either embed them into the `.ovpn` or extend the worker mount to the whole provider folder. Proton WireGuard configs typically work directly as `.conf`.

This first version intentionally runs location tests sequentially. Parallel tests would compete for WAN bandwidth and make throughput comparisons misleading.
