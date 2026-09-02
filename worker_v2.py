import json
import os
import random
import re
import socket
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CFG = Path(os.environ.get("VPN_CONFIG", "/vpn/config"))
TYPE = os.environ.get("VPN_TYPE", "auto").lower()
PROVIDER = os.environ.get("VPN_PROVIDER", "").strip().lower()
FORWARDED_PORT = int(os.environ.get("FORWARDED_PORT", "0") or 0)
BENCHMARK_MODE = os.environ.get("BENCHMARK_MODE", "smart").strip().lower()
if BENCHMARK_MODE not in {"smart", "deep"}:
    BENCHMARK_MODE = "smart"

PROFILE = {
    "smart": {
        "ping_count": 8,
        "iperf_duration": 7,
        "iperf_single_duration": 4,
        "peer_ping_count": 4,
        "peer_duration": 2,
        "iperf_max_tries": 2,
        "peer_max_tries": 2,
        "connect_timeout_ms": 2500,
        "raw_precheck_ping_count": 3,
    },
    "deep": {
        "ping_count": 20,
        "iperf_duration": 15,
        "iperf_single_duration": 8,
        "peer_ping_count": 6,
        "peer_duration": 3,
        "iperf_max_tries": 5,
        "peer_max_tries": 4,
        "connect_timeout_ms": 5000,
        "raw_precheck_ping_count": 5,
    },
}[BENCHMARK_MODE]

PING_COUNT = int(os.environ.get("PING_COUNT", str(PROFILE["ping_count"])))
IPERF_DURATION = int(os.environ.get("IPERF_DURATION", str(PROFILE["iperf_duration"])))
IPERF_SINGLE_DURATION = int(os.environ.get("IPERF_SINGLE_DURATION", str(PROFILE["iperf_single_duration"])))
IPERF_PARALLEL = int(os.environ.get("IPERF_PARALLEL", "4"))
PEER_PING_COUNT = int(os.environ.get("PEER_PING_COUNT", str(PROFILE["peer_ping_count"])))
PEER_DURATION = int(os.environ.get("PEER_DURATION", str(PROFILE["peer_duration"])))
PEER_PARALLEL = int(os.environ.get("PEER_PARALLEL", "2"))
IPERF_MAX_TRIES = int(os.environ.get("IPERF_MAX_TRIES", str(PROFILE["iperf_max_tries"])))
PEER_MAX_TRIES = int(os.environ.get("PEER_MAX_TRIES", str(PROFILE["peer_max_tries"])))
IPERF_CONNECT_TIMEOUT_MS = int(os.environ.get("IPERF_CONNECT_TIMEOUT_MS", str(PROFILE["connect_timeout_ms"])))
RAW_PRECHECK_PING_COUNT = int(os.environ.get("RAW_PRECHECK_PING_COUNT", str(PROFILE["raw_precheck_ping_count"])))
PROGRESS_PREFIX = "__PROGRESS__"

RAW_TARGETS = [
    {"key": "fra", "label": "Leaseweb Frankfurt", "host": "speedtest.fra1.de.leaseweb.net", "ports": list(range(5201, 5211))},
    {"key": "ams", "label": "Leaseweb Amsterdam", "host": "speedtest.ams1.nl.leaseweb.net", "ports": list(range(5201, 5211))},
]

# Peer probes intentionally span different networks/ASNs. Raw speed remains
# Leaseweb FRA/AMS; these targets are a connectivity proxy for typical EU
# datacenter/seedbox paths rather than another single-provider speed test.
PEER_REGIONS = [
    {"code": "NL", "label": "Netherlands", "city": "Amsterdam / Naaldwijk", "primary": {"label": "Worldstream Naaldwijk", "host": "iperf.worldstream.nl", "ports": list(range(5201, 5206))}, "secondary": {"label": "Clouvider Amsterdam", "host": "ams.speedtest.clouvider.net", "ports": list(range(5200, 5210))}},
    {"code": "DE", "label": "Germany", "city": "Frankfurt", "primary": {"label": "Clouvider Frankfurt", "host": "fra.speedtest.clouvider.net", "ports": list(range(5200, 5210))}, "secondary": {"label": "IP-Projects Frankfurt", "host": "speedtest.ip-projects.de", "ports": [5201]}},
    {"code": "CH", "label": "Switzerland", "city": "Zürich / Winterthur", "primary": {"label": "iWay Zürich", "host": "speedtest.iway.ch", "ports": [5201]}, "secondary": {"label": "Init7 Winterthur", "host": "speedtest.init7.net", "ports": list(range(5201, 5205))}},
    {"code": "DK", "label": "Denmark", "city": "Copenhagen", "primary": {"label": "Fiberby Copenhagen", "host": "speed1.fiberby.dk", "ports": list(range(9201, 9241))}, "secondary": {"label": "Hiper Copenhagen", "host": "speedtest.hiper.dk", "ports": list(range(5201, 5206))}},
    {"code": "SE", "label": "Sweden", "city": "Stockholm / Kista", "primary": {"label": "Kamel Kista", "host": "speedtest.kamel.network", "ports": list(range(5201, 5206))}, "secondary": {"label": "Stockholm public iPerf", "host": "185.76.9.135", "ports": [5201]}},
    {"code": "PL", "label": "Poland", "city": "Warsaw", "primary": {"label": "Warsaw public iPerf", "host": "185.246.208.67", "ports": [5201]}, "secondary": {"label": "Multinet24 Poland", "host": "speedsrv.multinet24.pl", "ports": list(range(5301, 5311))}},
    {"code": "RO", "label": "Romania", "city": "Bucharest", "primary": {"label": "Bucharest public iPerf", "host": "185.102.217.170", "ports": [5201]}, "secondary": None},
]


def progress(stage, label, percent, details=None):
    payload = {"stage": stage, "label": label, "percent": max(0, min(100, int(percent))), "ts": int(time.time())}
    if details is not None:
        payload["details"] = details
    print(PROGRESS_PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)


def run(cmd, timeout=30, check=False):
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if check and p.returncode != 0:
        details = "\n".join(x for x in [p.stdout.strip(), p.stderr.strip()] if x)
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{details}")
    return p


def vpn_type():
    if TYPE in {"wireguard", "openvpn", "none"}:
        return TYPE
    return "openvpn" if CFG.suffix.lower() == ".ovpn" else "wireguard"


def connect_wireguard():
    source = CFG.read_text(errors="strict")
    dns_servers, clean_lines = [], []
    for line in source.splitlines():
        m = re.match(r"^\s*DNS\s*=\s*(.+?)\s*$", line, flags=re.I)
        if m:
            dns_servers.extend(x.strip() for x in m.group(1).split(",") if x.strip())
        else:
            clean_lines.append(line)
    target = Path("/tmp/vpnbench.conf")
    target.write_text("\n".join(clean_lines) + "\n")
    target.chmod(0o600)
    resolv = Path("/etc/resolv.conf")
    try:
        original_resolv = resolv.read_text()
    except Exception:
        original_resolv = None
    run(["wg-quick", "up", str(target)], timeout=20, check=True)
    if dns_servers:
        try:
            resolv.write_text("".join(f"nameserver {server}\n" for server in dns_servers))
        except Exception:
            pass

    def cleanup():
        run(["wg-quick", "down", str(target)], timeout=10)
        if original_resolv is not None:
            try:
                resolv.write_text(original_resolv)
            except Exception:
                pass
    return cleanup


def connect_openvpn():
    log_path = Path("/tmp/openvpn.log")
    log = log_path.open("w")
    proc = subprocess.Popen(["openvpn", "--config", str(CFG), "--auth-nocache", "--verb", "3"], stdout=log, stderr=subprocess.STDOUT, text=True)
    deadline = time.time() + 25
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(1)
        try:
            if "Initialization Sequence Completed" in log_path.read_text(errors="ignore"):
                return lambda: proc.terminate()
        except Exception:
            pass
    try:
        proc.terminate()
    except Exception:
        pass
    txt = log_path.read_text(errors="ignore") if log_path.exists() else ""
    raise RuntimeError("OpenVPN connection failed: " + txt[-1500:])


def public_info():
    for url in ["https://ipinfo.io/json", "https://api.ipify.org?format=json"]:
        p = run(["curl", "-4", "-fsS", "--max-time", "10", url], timeout=15)
        if p.returncode == 0:
            try:
                data = json.loads(p.stdout)
                return {"ip": data.get("ip"), "city": data.get("city"), "region": data.get("region"), "country": data.get("country"), "org": data.get("org")}
            except Exception:
                pass
    return {"ip": None}


def ping_stats(host, count=None):
    count = int(count or PING_COUNT)
    p = run(["ping", "-4", "-c", str(count), "-i", "0.18", "-W", "2", host], timeout=max(12, count + 6))
    vals = [float(x) for x in re.findall(r"time[=<]([0-9.]+)\s*ms", p.stdout)]
    received = len(vals)
    loss = 100.0 * max(0, count - received) / max(count, 1)
    if not vals:
        return {"host": host, "sent": count, "received": 0, "avg_ms": None, "min_ms": None, "max_ms": None, "jitter_ms": None, "loss_pct": 100.0}
    diffs = [abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))]
    return {"host": host, "sent": count, "received": received, "avg_ms": round(statistics.mean(vals), 2), "min_ms": round(min(vals), 2), "max_ms": round(max(vals), 2), "jitter_ms": round(statistics.mean(diffs), 2) if diffs else 0.0, "loss_pct": round(loss, 2)}


def parallel_pings(items):
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=len(items)) as pool:
        futures = [pool.submit(ping_stats, host, count) for host, count in items]
        return [future.result() for future in futures]


def aggregate_ping(results):
    valid = [x for x in results if x.get("avg_ms") is not None]
    if not valid:
        return {"avg_ms": None, "jitter_ms": None, "loss_pct": 100.0, "targets": results}
    return {"avg_ms": round(statistics.mean(x["avg_ms"] for x in valid), 2), "jitter_ms": round(statistics.mean(x["jitter_ms"] for x in valid), 2), "loss_pct": round(statistics.mean(x["loss_pct"] for x in results), 2), "targets": results}


def iperf_once(host, ports, reverse=False, parallel=4, duration=15, max_tries=None):
    tries = int(max_tries or IPERF_MAX_TRIES)
    candidates = list(ports or [5201])
    random.shuffle(candidates)
    candidates = candidates[:tries]
    errors = []
    for port in candidates:
        cmd = [
            "iperf3", "-c", host, "-4", "-p", str(port),
            "--connect-timeout", str(IPERF_CONNECT_TIMEOUT_MS),
            "-P", str(parallel), "-t", str(duration), "-J",
        ]
        if reverse:
            cmd.append("-R")
        try:
            p = run(cmd, timeout=duration + (6 if BENCHMARK_MODE == "smart" else 10))
        except subprocess.TimeoutExpired:
            errors.append(f"{port}: timeout")
            continue
        if p.returncode != 0:
            errors.append(f"{port}: {(p.stderr or p.stdout).strip().replace(chr(10), ' ')[-160:]}")
            continue
        try:
            data = json.loads(p.stdout)
        except Exception:
            errors.append(f"{port}: invalid JSON")
            continue
        if data.get("error"):
            errors.append(f"{port}: {data['error']}")
            continue
        end = data.get("end", {})
        bucket = end.get("sum_received" if reverse else "sum_sent", {})
        bps = bucket.get("bits_per_second")
        if not bps:
            bps = end.get("sum_received", {}).get("bits_per_second") or end.get("sum_sent", {}).get("bits_per_second")
        if not bps:
            errors.append(f"{port}: no bitrate")
            continue
        return {"ok": True, "host": host, "port": port, "parallel": parallel, "seconds": duration, "mbps": round(float(bps) / 1_000_000, 2), "retransmits": end.get("sum_sent", {}).get("retransmits")}
    return {"ok": False, "host": host, "parallel": parallel, "seconds": duration, "mbps": None, "error": " | ".join(errors[-3:]) or "No reachable iPerf3 port"}


def raw_target_precheck():
    probes = parallel_pings([(target["host"], RAW_PRECHECK_PING_COUNT) for target in RAW_TARGETS])
    rows = []
    for target, probe in zip(RAW_TARGETS, probes):
        rows.append({"key": target["key"], "label": target["label"], "host": target["host"], "ping": probe})

    reachable = [row for row in rows if row["ping"].get("avg_ms") is not None]
    if not reachable:
        return RAW_TARGETS[0], rows

    best = min(reachable, key=lambda row: (float(row["ping"].get("loss_pct") or 100), float(row["ping"].get("avg_ms") or 9999)))
    selected = next(target for target in RAW_TARGETS if target["key"] == best["key"])
    return selected, rows


def raw_throughput_suite(progress_start=31, progress_end=66):
    targets = {}
    precheck = []
    if BENCHMARK_MODE == "smart":
        progress("raw_precheck", "Raw Speed · Frankfurt/Amsterdam werden kurz vorgeprüft", progress_start)
        selected, precheck = raw_target_precheck()
        run_targets = [selected]
        selected_key = selected["key"]
    else:
        run_targets = RAW_TARGETS
        selected_key = None

    span = (progress_end - progress_start) / max(len(run_targets), 1)
    for idx, target in enumerate(run_targets):
        base = progress_start + idx * span
        key, host, ports = target["key"], target["host"], target["ports"]
        targets[key] = {"label": target["label"], "host": host}
        progress(f"raw_{key}_single", f"Raw Speed · {target['label']}: Single Download", base + 1)
        targets[key]["single_down"] = iperf_once(host, ports, reverse=True, parallel=1, duration=IPERF_SINGLE_DURATION)
        progress(f"raw_{key}_down", f"Raw Speed · {target['label']}: 4× Download", base + span * 0.34)
        targets[key]["multi_down"] = iperf_once(host, ports, reverse=True, parallel=IPERF_PARALLEL, duration=IPERF_DURATION)
        progress(f"raw_{key}_up", f"Raw Speed · {target['label']}: 4× Upload", base + span * 0.7)
        targets[key]["multi_up"] = iperf_once(host, ports, reverse=False, parallel=IPERF_PARALLEL, duration=IPERF_DURATION)

    def med(path):
        vals = [float(item[path]["mbps"]) for item in targets.values() if item.get(path, {}).get("mbps") is not None]
        return round(statistics.median(vals), 2) if vals else None

    return {
        "download_mbps": med("multi_down"),
        "upload_mbps": med("multi_up"),
        "single_download_mbps": med("single_down"),
        "targets": targets,
        "benchmark_mode": BENCHMARK_MODE,
        "selected_target": selected_key,
        "precheck": precheck,
    }


def iperf_region_direction(region, reverse=False):
    endpoints = [region["primary"]]
    if region.get("secondary"):
        endpoints.append(region["secondary"])

    attempts = []
    for endpoint in endpoints:
        result = iperf_once(
            endpoint["host"],
            endpoint["ports"],
            reverse=reverse,
            parallel=PEER_PARALLEL,
            duration=PEER_DURATION,
            max_tries=PEER_MAX_TRIES,
        )
        result["target_label"] = endpoint["label"]
        attempts.append(dict(result))
        if result.get("ok"):
            result["attempts"] = attempts
            return result

    failed = dict(attempts[-1]) if attempts else {"ok": False, "mbps": None, "error": "No peer endpoint configured"}
    failed["attempts"] = attempts
    return failed


def peer_region_probe(region):
    primary = region["primary"]
    secondary = region.get("secondary")
    ping_inputs = [(primary["host"], PEER_PING_COUNT)]
    if secondary:
        ping_inputs.append((secondary["host"], max(3, PEER_PING_COUNT - 1)))
    ping_results = parallel_pings(ping_inputs)

    networks = [{"label": primary["label"], "host": primary["host"], "role": "primary", "ping": ping_results[0]}]
    if secondary:
        networks.append({"label": secondary["label"], "host": secondary["host"], "role": "secondary", "ping": ping_results[1]})

    down = iperf_region_direction(region, reverse=True)
    up = iperf_region_direction(region, reverse=False)
    aggregate = aggregate_ping(ping_results)
    return {
        "code": region["code"],
        "label": region["label"],
        "city": region["city"],
        "primary": primary["label"],
        "download_mbps": down.get("mbps"),
        "upload_mbps": up.get("mbps"),
        "download": down,
        "upload": up,
        "download_target": down.get("target_label"),
        "upload_target": up.get("target_label"),
        "ping_ms": aggregate.get("avg_ms"),
        "jitter_ms": aggregate.get("jitter_ms"),
        "loss_pct": aggregate.get("loss_pct"),
        "networks": networks,
    }


def peer_connectivity_suite(progress_start=67, progress_end=91):
    regions = {}
    span = (progress_end - progress_start) / max(len(PEER_REGIONS), 1)
    for idx, region in enumerate(PEER_REGIONS):
        pct = progress_start + idx * span
        progress(f"peer_{region['code'].lower()}", f"EU Peer · {region['code']} {region['city']} wird geprüft", pct, {"region": region["code"]})
        result = peer_region_probe(region)
        regions[region["code"]] = result
        progress(f"peer_{region['code'].lower()}_done", f"EU Peer · {region['code']} abgeschlossen", pct + span * 0.9, {"region": region["code"], "download_mbps": result.get("download_mbps"), "upload_mbps": result.get("upload_mbps"), "ping_ms": result.get("ping_ms"), "loss_pct": result.get("loss_pct")})
    return {"regions": regions, "target_order": [r["code"] for r in PEER_REGIONS], "method": "short multi-network iPerf3 + ICMP probes", "benchmark_mode": BENCHMARK_MODE}


def dns_test():
    t = time.time()
    p = run(["nslookup", "cloudflare.com"], timeout=10)
    return {"ok": p.returncode == 0, "ms": round((time.time() - t) * 1000, 1)}


def _listener(port, ready, stop):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port)); srv.listen(4); srv.settimeout(0.5); ready.set()
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
                try: conn.sendall(b"vpn-exit-bench\n")
                except Exception: pass
                conn.close()
            except socket.timeout:
                pass
    finally:
        srv.close()


def tcp_portcheck(port, public_port=None):
    if not port:
        return {"verified": False, "open": None, "error": "No port supplied"}
    ready, stop = threading.Event(), threading.Event()
    thread = threading.Thread(target=_listener, args=(port, ready, stop), daemon=True); thread.start()
    if not ready.wait(2):
        stop.set(); return {"verified": False, "open": None, "error": f"Could not listen on TCP {port}"}
    check_port = int(public_port or port)
    try:
        p = run(["curl", "-4", "-fsS", "--max-time", "12", f"http://portcheck.transmissionbt.com/{check_port}"], timeout=15)
        value = p.stdout.strip()
        if p.returncode == 0 and value in {"0", "1"}:
            return {"verified": True, "open": value == "1", "checker": "portcheck.transmissionbt.com"}
        return {"verified": False, "open": None, "error": (p.stderr or p.stdout).strip()[-300:]}
    finally:
        stop.set(); thread.join(timeout=1)


def proton_port_forwarding():
    gateway = "10.2.0.1"
    probe = run(["natpmpc", "-g", gateway], timeout=8)
    if probe.returncode != 0:
        return {"status": "closed", "supported": False, "verified": True, "provider_method": "NAT-PMP", "error": (probe.stderr or probe.stdout).strip()[-500:]}
    tcp = run(["natpmpc", "-a", "1", "0", "tcp", "60", "-g", gateway], timeout=8)
    txt = "\n".join([tcp.stdout, tcp.stderr])
    m = re.search(r"Mapped public port\s+(\d+)", txt, flags=re.I)
    if tcp.returncode != 0 or not m:
        return {"status": "closed", "supported": True, "verified": True, "provider_method": "NAT-PMP", "error": txt.strip()[-500:]}
    public_port = int(m.group(1))
    udp = run(["natpmpc", "-a", "1", str(public_port), "udp", "60", "-g", gateway], timeout=8)
    external = tcp_portcheck(1, public_port=public_port)
    status = "open" if external.get("verified") and external.get("open") else "mapped_unverified"
    return {"status": status, "supported": True, "verified": external.get("verified", False), "tcp_open": external.get("open"), "udp_mapping": udp.returncode == 0, "public_port": public_port, "provider_method": "NAT-PMP", "checker": external.get("checker"), "error": external.get("error")}


def generic_forwarded_port_check():
    if FORWARDED_PORT <= 0:
        return {"status": "unknown", "supported": None, "verified": False, "provider_method": "manual", "note": "No forwarded port supplied for this config."}
    result = tcp_portcheck(FORWARDED_PORT)
    status = "open" if result.get("verified") and result.get("open") else "closed" if result.get("verified") else "unknown"
    return {"status": status, "supported": None, "verified": result.get("verified", False), "tcp_open": result.get("open"), "public_port": FORWARDED_PORT, "provider_method": "manual", "checker": result.get("checker"), "error": result.get("error")}


def port_forwarding_test():
    return proton_port_forwarding() if PROVIDER == "proton" else generic_forwarded_port_check()


def main():
    kind = vpn_type()
    out = {
        "ok": False,
        "config": CFG.name if kind != "none" else "DIRECT",
        "type": kind,
        "provider_hint": PROVIDER,
        "started_at": int(time.time()),
        "benchmark_version": 3,
        "benchmark_mode": BENCHMARK_MODE,
    }
    cleanup = None
    try:
        progress("starting", f"Worker gestartet · {BENCHMARK_MODE.upper()} Run", 1, {"benchmark_mode": BENCHMARK_MODE})
        before = public_info(); out["ip_before"] = before
        progress("ip_before_done", "Ausgangs-IP ermittelt", 4, {"ip": before.get("ip")})
        if kind == "wireguard":
            progress("vpn_connect", "WireGuard-Tunnel wird aufgebaut", 6); cleanup = connect_wireguard(); progress("vpn_connected", "WireGuard-Tunnel steht", 10)
        elif kind == "openvpn":
            progress("vpn_connect", "OpenVPN-Tunnel wird aufgebaut", 6); cleanup = connect_openvpn(); progress("vpn_connected", "OpenVPN-Tunnel steht", 10)
        else:
            progress("direct", "Direktleitung – kein VPN", 10)
        time.sleep(2 if kind != "none" else 0.2)
        after = public_info(); out["exit"] = after
        out["ok"] = bool(after.get("ip")) if kind == "none" else bool(after.get("ip") and after.get("ip") != before.get("ip"))
        progress("exit_ip_done", "Exit-IP geprüft", 14, {"ip": after.get("ip"), "city": after.get("city"), "country": after.get("country")})

        progress("ping_pair", f"Ping 1.1.1.1 + 8.8.8.8 ({PING_COUNT} Pakete, parallel)", 17)
        ping_cf, ping_google = parallel_pings([("1.1.1.1", PING_COUNT), ("8.8.8.8", PING_COUNT)])
        out["ping"] = aggregate_ping([ping_cf, ping_google])
        progress("dns", "DNS-Auflösung wird getestet", 23); out["dns"] = dns_test()

        out["throughput"] = raw_throughput_suite(27, 59 if kind != "none" else 94)
        out["download"] = {"mbps": out["throughput"].get("download_mbps")}
        out["upload"] = {"mbps": out["throughput"].get("upload_mbps")}
        progress("raw_done", "Raw-Speed-Tests abgeschlossen", 60 if kind != "none" else 95, {"download_mbps": out["throughput"].get("download_mbps"), "upload_mbps": out["throughput"].get("upload_mbps"), "benchmark_mode": BENCHMARK_MODE})

        if kind != "none":
            out["peer_connectivity"] = peer_connectivity_suite(61, 89)
            progress("port", "Port Forwarding / Erreichbarkeit wird geprüft", 91)
            out["port_forwarding"] = port_forwarding_test()
            progress("port_done", "Port-Prüfung abgeschlossen", 97, out["port_forwarding"])
        if kind != "none" and not out["ok"]:
            out["warning"] = "Public IP did not change or could not be verified."
        progress("finalizing", "Ergebnis wird ausgewertet", 99)
    except Exception as e:
        out["error"] = str(e); progress("error", "Benchmark fehlgeschlagen", 100, {"error": str(e)})
    finally:
        if cleanup:
            try: cleanup()
            except Exception: pass
    out["finished_at"] = int(time.time()); out["duration_s"] = out["finished_at"] - out["started_at"]
    if not out.get("error"):
        progress("done", "Benchmark abgeschlossen", 100, {"download_mbps": (out.get("throughput") or {}).get("download_mbps"), "upload_mbps": (out.get("throughput") or {}).get("upload_mbps"), "benchmark_mode": BENCHMARK_MODE})
    print(json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
