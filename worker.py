import json
import os
import random
import re
import socket
import statistics
import subprocess
import threading
import time
from pathlib import Path

CFG = Path(os.environ.get("VPN_CONFIG", "/vpn/config"))
TYPE = os.environ.get("VPN_TYPE", "auto").lower()
PROVIDER = os.environ.get("VPN_PROVIDER", "").strip().lower()
FORWARDED_PORT = int(os.environ.get("FORWARDED_PORT", "0") or 0)
PING_COUNT = int(os.environ.get("PING_COUNT", "20"))
IPERF_DURATION = int(os.environ.get("IPERF_DURATION", "15"))
IPERF_SINGLE_DURATION = int(os.environ.get("IPERF_SINGLE_DURATION", "8"))
IPERF_PARALLEL = int(os.environ.get("IPERF_PARALLEL", "4"))

IPERF_TARGETS = [
    {"key": "fra", "label": "Leaseweb Frankfurt", "host": "speedtest.fra1.de.leaseweb.net"},
    {"key": "ams", "label": "Leaseweb Amsterdam", "host": "speedtest.ams1.nl.leaseweb.net"},
]


def run(cmd, timeout=30, check=False):
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if check and p.returncode != 0:
        details = "\n".join(x for x in [p.stdout.strip(), p.stderr.strip()] if x)
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{details}")
    return p


def vpn_type():
    if TYPE in {"wireguard", "openvpn", "none"}:
        return TYPE
    if CFG.suffix.lower() == ".ovpn":
        return "openvpn"
    return "wireguard"


def connect_wireguard():
    source = CFG.read_text(errors="strict")
    dns_servers = []
    clean_lines = []

    for line in source.splitlines():
        m = re.match(r"^\s*DNS\s*=\s*(.+?)\s*$", line, flags=re.I)
        if m:
            dns_servers.extend(x.strip() for x in m.group(1).split(",") if x.strip())
            continue
        clean_lines.append(line)

    target = Path("/tmp/vpnbench.conf")
    target.write_text("\n".join(clean_lines) + "\n")
    target.chmod(0o600)

    resolv = Path("/etc/resolv.conf")
    original_resolv = None
    try:
        original_resolv = resolv.read_text()
    except Exception:
        pass

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
    proc = subprocess.Popen(
        ["openvpn", "--config", str(CFG), "--auth-nocache", "--verb", "3"],
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 25

    while time.time() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(1)
        try:
            txt = log_path.read_text(errors="ignore")
            if "Initialization Sequence Completed" in txt:
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
    urls = [
        "https://ipinfo.io/json",
        "https://api.ipify.org?format=json",
    ]
    for url in urls:
        p = run(["curl", "-4", "-fsS", "--max-time", "10", url], timeout=15)
        if p.returncode == 0:
            try:
                data = json.loads(p.stdout)
                return {
                    "ip": data.get("ip"),
                    "city": data.get("city"),
                    "region": data.get("region"),
                    "country": data.get("country"),
                    "org": data.get("org"),
                }
            except Exception:
                pass
    return {"ip": None}


def ping_stats(host):
    p = run(
        ["ping", "-4", "-c", str(PING_COUNT), "-i", "0.2", "-W", "2", host],
        timeout=max(15, PING_COUNT + 8),
    )
    vals = [float(x) for x in re.findall(r"time[=<]([0-9.]+)\s*ms", p.stdout)]
    received = len(vals)
    loss = 100.0 * max(0, PING_COUNT - received) / PING_COUNT

    if not vals:
        return {
            "host": host,
            "sent": PING_COUNT,
            "received": 0,
            "avg_ms": None,
            "min_ms": None,
            "max_ms": None,
            "jitter_ms": None,
            "loss_pct": 100.0,
        }

    diffs = [abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))]
    return {
        "host": host,
        "sent": PING_COUNT,
        "received": received,
        "avg_ms": round(statistics.mean(vals), 2),
        "min_ms": round(min(vals), 2),
        "max_ms": round(max(vals), 2),
        "jitter_ms": round(statistics.mean(diffs), 2) if diffs else 0.0,
        "loss_pct": round(loss, 2),
    }


def aggregate_ping(results):
    valid = [x for x in results if x.get("avg_ms") is not None]
    if not valid:
        return {
            "avg_ms": None,
            "jitter_ms": None,
            "loss_pct": 100.0,
            "targets": results,
        }
    return {
        "avg_ms": round(statistics.mean(x["avg_ms"] for x in valid), 2),
        "jitter_ms": round(statistics.mean(x["jitter_ms"] for x in valid), 2),
        "loss_pct": round(statistics.mean(x["loss_pct"] for x in results), 2),
        "targets": results,
    }


def iperf_once(host, reverse=False, parallel=4, duration=15):
    ports = list(range(5201, 5211))
    random.shuffle(ports)
    errors = []

    for port in ports:
        cmd = [
            "iperf3",
            "-c",
            host,
            "-4",
            "-p",
            str(port),
            "-P",
            str(parallel),
            "-t",
            str(duration),
            "-J",
        ]
        if reverse:
            cmd.append("-R")

        try:
            p = run(cmd, timeout=duration + 15)
        except subprocess.TimeoutExpired:
            errors.append(f"{port}: timeout")
            continue

        if p.returncode != 0:
            err = (p.stderr or p.stdout).strip().replace("\n", " ")
            errors.append(f"{port}: {err[-160:]}")
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
            for key in ("sum_received", "sum_sent"):
                candidate = end.get(key, {}).get("bits_per_second")
                if candidate:
                    bps = candidate
                    break

        if not bps:
            errors.append(f"{port}: no bitrate in result")
            continue

        return {
            "ok": True,
            "host": host,
            "port": port,
            "parallel": parallel,
            "seconds": duration,
            "mbps": round(float(bps) / 1_000_000, 2),
            "retransmits": end.get("sum_sent", {}).get("retransmits"),
        }

    return {
        "ok": False,
        "host": host,
        "parallel": parallel,
        "seconds": duration,
        "mbps": None,
        "error": " | ".join(errors[-3:]) or "No free iperf3 port",
    }


def throughput_suite():
    targets = {}
    for target in IPERF_TARGETS:
        host = target["host"]
        targets[target["key"]] = {
            "label": target["label"],
            "host": host,
            "single_down": iperf_once(
                host,
                reverse=True,
                parallel=1,
                duration=IPERF_SINGLE_DURATION,
            ),
            "multi_down": iperf_once(
                host,
                reverse=True,
                parallel=IPERF_PARALLEL,
                duration=IPERF_DURATION,
            ),
            "multi_up": iperf_once(
                host,
                reverse=False,
                parallel=IPERF_PARALLEL,
                duration=IPERF_DURATION,
            ),
        }

    def med(path):
        vals = []
        for item in targets.values():
            v = item.get(path, {}).get("mbps")
            if v is not None:
                vals.append(float(v))
        return round(statistics.median(vals), 2) if vals else None

    return {
        "download_mbps": med("multi_down"),
        "upload_mbps": med("multi_up"),
        "single_download_mbps": med("single_down"),
        "targets": targets,
    }


def dns_test():
    t = time.time()
    p = run(["nslookup", "cloudflare.com"], timeout=10)
    return {
        "ok": p.returncode == 0,
        "ms": round((time.time() - t) * 1000, 1),
    }


def _listener(port, ready, stop):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
        srv.listen(4)
        srv.settimeout(0.5)
        ready.set()
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
                try:
                    conn.sendall(b"vpn-exit-bench\n")
                except Exception:
                    pass
                conn.close()
            except socket.timeout:
                pass
    finally:
        srv.close()


def tcp_portcheck(port, public_port=None):
    if not port:
        return {"verified": False, "open": None, "error": "No port supplied"}

    ready = threading.Event()
    stop = threading.Event()
    thread = threading.Thread(target=_listener, args=(port, ready, stop), daemon=True)
    thread.start()

    if not ready.wait(2):
        stop.set()
        return {"verified": False, "open": None, "error": f"Could not listen on TCP {port}"}

    check_port = int(public_port or port)
    try:
        p = run(
            ["curl", "-4", "-fsS", "--max-time", "12", f"http://portcheck.transmissionbt.com/{check_port}"],
            timeout=15,
        )
        value = p.stdout.strip()
        if p.returncode == 0 and value in {"0", "1"}:
            return {
                "verified": True,
                "open": value == "1",
                "checker": "portcheck.transmissionbt.com",
            }
        return {
            "verified": False,
            "open": None,
            "error": (p.stderr or p.stdout).strip()[-300:],
        }
    finally:
        stop.set()
        thread.join(timeout=1)


def proton_port_forwarding():
    gateway = "10.2.0.1"
    probe = run(["natpmpc", "-g", gateway], timeout=8)
    if probe.returncode != 0:
        return {
            "status": "closed",
            "supported": False,
            "verified": True,
            "provider_method": "NAT-PMP",
            "error": (probe.stderr or probe.stdout).strip()[-500:],
        }

    tcp = run(["natpmpc", "-a", "1", "0", "tcp", "60", "-g", gateway], timeout=8)
    txt = "\n".join([tcp.stdout, tcp.stderr])
    m = re.search(r"Mapped public port\s+(\d+)", txt, flags=re.I)
    if tcp.returncode != 0 or not m:
        return {
            "status": "closed",
            "supported": True,
            "verified": True,
            "provider_method": "NAT-PMP",
            "error": txt.strip()[-500:],
        }

    public_port = int(m.group(1))
    udp = run(
        ["natpmpc", "-a", "1", str(public_port), "udp", "60", "-g", gateway],
        timeout=8,
    )
    udp_ok = udp.returncode == 0
    external = tcp_portcheck(1, public_port=public_port)

    if external.get("verified") and external.get("open"):
        status = "open"
    else:
        status = "mapped_unverified"

    return {
        "status": status,
        "supported": True,
        "verified": external.get("verified", False),
        "tcp_open": external.get("open"),
        "udp_mapping": udp_ok,
        "public_port": public_port,
        "provider_method": "NAT-PMP",
        "checker": external.get("checker"),
        "error": external.get("error"),
    }


def generic_forwarded_port_check():
    if FORWARDED_PORT <= 0:
        return {
            "status": "unknown",
            "supported": None,
            "verified": False,
            "provider_method": "manual",
            "note": "No forwarded port supplied for this config.",
        }

    result = tcp_portcheck(FORWARDED_PORT)
    if result.get("verified"):
        status = "open" if result.get("open") else "closed"
    else:
        status = "unknown"

    return {
        "status": status,
        "supported": None,
        "verified": result.get("verified", False),
        "tcp_open": result.get("open"),
        "public_port": FORWARDED_PORT,
        "provider_method": "manual",
        "checker": result.get("checker"),
        "error": result.get("error"),
    }


def port_forwarding_test():
    if PROVIDER == "proton":
        return proton_port_forwarding()
    return generic_forwarded_port_check()


def main():
    kind = vpn_type()
    out = {
        "ok": False,
        "config": CFG.name if kind != "none" else "DIRECT",
        "type": kind,
        "provider_hint": PROVIDER,
        "started_at": int(time.time()),
    }
    cleanup = None

    try:
        before = public_info()
        out["ip_before"] = before

        if kind == "wireguard":
            cleanup = connect_wireguard()
        elif kind == "openvpn":
            cleanup = connect_openvpn()

        time.sleep(2 if kind != "none" else 0.2)
        after = public_info()
        out["exit"] = after

        if kind == "none":
            out["ok"] = bool(after.get("ip"))
        else:
            out["ok"] = bool(after.get("ip") and after.get("ip") != before.get("ip"))

        ping_results = [ping_stats("1.1.1.1"), ping_stats("8.8.8.8")]
        out["ping"] = aggregate_ping(ping_results)
        out["dns"] = dns_test()
        out["throughput"] = throughput_suite()
        out["download"] = {"mbps": out["throughput"].get("download_mbps")}
        out["upload"] = {"mbps": out["throughput"].get("upload_mbps")}

        if kind != "none":
            out["port_forwarding"] = port_forwarding_test()

        if kind != "none" and not out["ok"]:
            out["warning"] = "Public IP did not change or could not be verified."

    except Exception as e:
        out["error"] = str(e)
    finally:
        if cleanup:
            try:
                cleanup()
            except Exception:
                pass

    out["finished_at"] = int(time.time())
    out["duration_s"] = out["finished_at"] - out["started_at"]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
