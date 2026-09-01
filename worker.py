import json, os, re, subprocess, time, statistics
from pathlib import Path

CFG = Path(os.environ.get("VPN_CONFIG", "/vpn/config"))
TYPE = os.environ.get("VPN_TYPE", "auto").lower()
DOWNLOAD_BYTES = int(os.environ.get("DOWNLOAD_BYTES", str(100 * 1024 * 1024)))
PING_HOST = os.environ.get("PING_HOST", "1.1.1.1")
TIMEOUT = int(os.environ.get("TEST_TIMEOUT", "45"))


def run(cmd, timeout=30, check=False):
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if check and p.returncode != 0:
        details = "\n".join(x for x in [p.stdout.strip(), p.stderr.strip()] if x)
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{details}")
    return p


def vpn_type():
    if TYPE in {"wireguard", "openvpn"}:
        return TYPE
    if CFG.suffix.lower() == ".ovpn":
        return "openvpn"
    return "wireguard"


def connect_wireguard():
    # wg-quick's DNS= handling expects a host init/resolvconf integration which
    # is intentionally absent inside the short-lived Alpine worker. Strip DNS=
    # from the temporary config and apply the requested DNS servers ourselves.
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
    log = open("/tmp/openvpn.log", "w")
    proc = subprocess.Popen([
        "openvpn", "--config", str(CFG), "--auth-nocache", "--verb", "3"
    ], stdout=log, stderr=subprocess.STDOUT, text=True)
    deadline = time.time() + 25
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(1)
        try:
            txt = Path("/tmp/openvpn.log").read_text(errors="ignore")
            if "Initialization Sequence Completed" in txt:
                return lambda: proc.terminate()
        except Exception:
            pass
    try:
        proc.terminate()
    except Exception:
        pass
    txt = Path("/tmp/openvpn.log").read_text(errors="ignore") if Path("/tmp/openvpn.log").exists() else ""
    raise RuntimeError("OpenVPN connection failed: " + txt[-1500:])


def public_info():
    urls = [
        "https://ipinfo.io/json",
        "https://api.ipify.org?format=json"
    ]
    for u in urls:
        p = run(["curl", "-4", "-fsS", "--max-time", "10", u], timeout=15)
        if p.returncode == 0:
            try:
                data = json.loads(p.stdout)
                return {
                    "ip": data.get("ip"), "city": data.get("city"),
                    "region": data.get("region"), "country": data.get("country"),
                    "org": data.get("org")
                }
            except Exception:
                pass
    return {"ip": None}


def ping_stats(host):
    p = run(["ping", "-4", "-c", "8", "-W", "2", host], timeout=22)
    vals = [float(x) for x in re.findall(r"time=([0-9.]+) ms", p.stdout)]
    if not vals:
        return {"avg_ms": None, "min_ms": None, "max_ms": None, "jitter_ms": None, "loss_pct": 100.0}
    loss = 100.0 * (8 - len(vals)) / 8
    diffs = [abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))]
    return {
        "avg_ms": round(statistics.mean(vals), 2), "min_ms": round(min(vals), 2),
        "max_ms": round(max(vals), 2), "jitter_ms": round(statistics.mean(diffs), 2) if diffs else 0,
        "loss_pct": round(loss, 1)
    }


def download_test():
    url = f"https://speed.cloudflare.com/__down?bytes={DOWNLOAD_BYTES}"
    p = run(["curl", "-4", "-L", "-sS", "-o", "/dev/null", "--max-time", str(TIMEOUT),
             "-w", "%{speed_download} %{time_total}", url], timeout=TIMEOUT + 5)
    if p.returncode != 0:
        return {"mbps": None, "seconds": None, "error": p.stderr.strip()[-300:]}
    try:
        bps, secs = p.stdout.strip().split()[:2]
        mbps = float(bps) * 8 / 1_000_000
        return {"mbps": round(mbps, 2), "seconds": round(float(secs), 2)}
    except Exception:
        return {"mbps": None, "seconds": None}


def dns_test():
    t = time.time()
    p = run(["nslookup", "cloudflare.com"], timeout=10)
    return {"ok": p.returncode == 0, "ms": round((time.time() - t) * 1000, 1)}


def main():
    out = {"ok": False, "config": CFG.name, "type": vpn_type(), "started_at": int(time.time())}
    cleanup = None
    try:
        before = public_info()
        out["ip_before"] = before
        cleanup = connect_wireguard() if vpn_type() == "wireguard" else connect_openvpn()
        time.sleep(2)
        after = public_info()
        out["exit"] = after
        out["ping"] = ping_stats(PING_HOST)
        out["dns"] = dns_test()
        out["download"] = download_test()
        out["ok"] = bool(after.get("ip") and after.get("ip") != before.get("ip"))
        if not out["ok"]:
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
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
