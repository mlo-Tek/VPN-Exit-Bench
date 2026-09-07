import math
import re
import statistics
import subprocess
import time

import worker_v2 as base


RAW_TARGETS = [
    {"key": "fra_leaseweb", "label": "Leaseweb Frankfurt", "host": "speedtest.fra1.de.leaseweb.net", "ports": list(range(5201, 5211))},
    {"key": "fra_clouvider", "label": "Clouvider Frankfurt", "host": "fra.speedtest.clouvider.net", "ports": list(range(5200, 5210))},
    {"key": "ams_clouvider", "label": "Clouvider Amsterdam", "host": "ams.speedtest.clouvider.net", "ports": list(range(5200, 5210))},
    {"key": "ams_eranium", "label": "Eranium Amsterdam", "host": "iperf-ams-nl.eranium.net", "ports": list(range(5201, 5211))},
]

# Reverse-mode iPerf on public servers is not uniformly reliable. Some servers
# heavily throttle or mishandle -R while normal client->server throughput stays
# healthy. When every selected reverse iPerf target looks suspiciously slow,
# verify raw download with ordinary HTTPS against Hetzner's documented speed
# test files. This is only a fallback, so normal fast runs remain fast.
HTTP_DOWNLOAD_TARGETS = [
    {"key": "hetzner_fsn", "label": "Hetzner Falkenstein", "url": "https://fsn1-speed.hetzner.com/100MB.bin"},
    {"key": "hetzner_nbg", "label": "Hetzner Nürnberg", "url": "https://nbg1-speed.hetzner.com/100MB.bin"},
]

SMART = base.BENCHMARK_MODE == "smart"
SMART_PEER_FALLBACK_MBPS = 80.0
SMART_HTTP_FALLBACK_MBPS = 80.0
PEER_REVERSE_UNTRUSTED_MBPS = 20.0
PEER_REVERSE_MIN_UPLOAD_MBPS = 80.0
PEER_REVERSE_MAX_RATIO = 0.20


def reliable_ping_stats(host, count=None):
    requested = int(count or base.PING_COUNT)
    sample_count = max(requested, 12 if requested >= base.PING_COUNT else 6)
    p = base.run(
        ["ping", "-4", "-c", str(sample_count), "-i", "0.35", "-W", "2", host],
        timeout=max(12, int(sample_count * 0.5) + 6),
    )
    vals = [float(x) for x in re.findall(r"time[=<]([0-9.]+)\s*ms", p.stdout)]
    received = len(vals)
    loss = 100.0 * max(0, sample_count - received) / max(sample_count, 1)
    if not vals:
        return {"host": host, "sent": sample_count, "received": 0, "avg_ms": None, "min_ms": None, "max_ms": None, "jitter_ms": None, "loss_pct": 100.0}
    diffs = [abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))]
    return {
        "host": host,
        "sent": sample_count,
        "received": received,
        "avg_ms": round(statistics.median(vals), 2),
        "min_ms": round(min(vals), 2),
        "max_ms": round(max(vals), 2),
        "jitter_ms": round(statistics.median(diffs), 2) if diffs else 0.0,
        "loss_pct": round(loss, 2),
    }


def robust_aggregate_ping(results):
    valid = [x for x in results if x.get("avg_ms") is not None]
    if not valid:
        return {"avg_ms": None, "jitter_ms": None, "loss_pct": 100.0, "targets": results}
    losses = [float(x.get("loss_pct", 100.0)) for x in valid]
    jitters = [float(x.get("jitter_ms", 0.0)) for x in valid if x.get("jitter_ms") is not None]
    return {
        "avg_ms": round(statistics.median(float(x["avg_ms"]) for x in valid), 2),
        "jitter_ms": round(statistics.median(jitters), 2) if jitters else None,
        "loss_pct": round(min(losses), 2),
        "targets": results,
    }


def reliable_dns_test():
    started = time.time()
    try:
        p = base.run(["nslookup", "cloudflare.com"], timeout=5)
        return {
            "ok": p.returncode == 0,
            "ms": round((time.time() - started) * 1000, 1),
            "error": None if p.returncode == 0 else (p.stderr or p.stdout).strip()[-300:],
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "ms": round((time.time() - started) * 1000, 1),
            "error": "DNS lookup timed out",
        }
    except Exception as exc:
        return {
            "ok": False,
            "ms": round((time.time() - started) * 1000, 1),
            "error": str(exc),
        }


def _quick_probe(target):
    return base.iperf_once(
        target["host"],
        target["ports"],
        reverse=True,
        parallel=2,
        duration=1 if SMART else 2,
        max_tries=1 if SMART else max(3, base.IPERF_MAX_TRIES),
    )


def _http_download_once(target, max_time=None):
    limit = int(max_time or (5 if SMART else 8))
    cmd = [
        "curl", "-4", "-L", "-sS",
        "--connect-timeout", "3",
        "--max-time", str(limit),
        "-o", "/dev/null",
        "-w", "%{speed_download} %{size_download}",
        target["url"],
    ]
    try:
        p = base.run(cmd, timeout=limit + 2)
    except subprocess.TimeoutExpired:
        return {"ok": False, "label": target["label"], "url": target["url"], "mbps": None, "error": "HTTP download timed out"}
    try:
        speed_bps, size_bytes = [float(x) for x in p.stdout.strip().split()[-2:]]
    except Exception:
        return {"ok": False, "label": target["label"], "url": target["url"], "mbps": None, "error": (p.stderr or p.stdout).strip()[-300:] or "No HTTP speed result"}
    if size_bytes < 1_000_000 or speed_bps <= 0:
        return {"ok": False, "label": target["label"], "url": target["url"], "mbps": None, "bytes": int(size_bytes), "error": (p.stderr or "Too little data downloaded").strip()[-300:]}
    return {
        "ok": True,
        "label": target["label"],
        "url": target["url"],
        "mbps": round(speed_bps * 8.0 / 1_000_000.0, 2),
        "bytes": int(size_bytes),
        "curl_exit": p.returncode,
    }


def _best_http_download(results):
    values = [float(row["mbps"]) for row in results if row.get("ok") and row.get("mbps") is not None]
    return round(max(values), 2) if values else None


def _reverse_download_trustworthy(download_mbps, upload_mbps):
    if download_mbps is None or upload_mbps is None:
        return True
    down = float(download_mbps)
    up = float(upload_mbps)
    if up < PEER_REVERSE_MIN_UPLOAD_MBPS:
        return True
    return not (down < PEER_REVERSE_UNTRUSTED_MBPS and down < up * PEER_REVERSE_MAX_RATIO)


def raw_throughput_suite(progress_start=31, progress_end=66):
    precheck = []
    base.progress("raw_precheck", "Raw Speed · unabhängige Testnetze werden vorgeprüft", progress_start)

    for target in RAW_TARGETS:
        down = _quick_probe(target)
        precheck.append({
            "key": target["key"],
            "label": target["label"],
            "host": target["host"],
            "download": down,
            "score": float(down.get("mbps") or 0.0) if down.get("ok") else 0.0,
        })

    healthy = sorted((row for row in precheck if row["score"] > 0), key=lambda row: row["score"], reverse=True)
    selected_keys = [row["key"] for row in healthy[:2]]
    if not selected_keys:
        selected_keys = [RAW_TARGETS[0]["key"]]
    selected = [target for target in RAW_TARGETS if target["key"] in selected_keys]

    targets = {}
    full_down = []
    span = (progress_end - progress_start) / max(len(selected), 1)
    full_tries = base.IPERF_MAX_TRIES if SMART else max(3, base.IPERF_MAX_TRIES)

    for idx, target in enumerate(selected):
        pct = progress_start + idx * span
        key, host, ports = target["key"], target["host"], target["ports"]
        targets[key] = {"label": target["label"], "host": host}
        base.progress(f"raw_{key}_down", f"Raw Speed · {target['label']}: Multi Download", pct + 1)
        result = base.iperf_stable(
            host, ports, reverse=True, parallel=base.IPERF_PARALLEL,
            duration=base.IPERF_DURATION, max_tries=full_tries,
        )
        targets[key]["multi_down"] = result
        if result.get("ok") and result.get("mbps") is not None:
            full_down.append((float(result["mbps"]), target))

    winner = max(full_down, key=lambda item: item[0])[1] if full_down else selected[0]
    key, host, ports = winner["key"], winner["host"], winner["ports"]
    base.progress(f"raw_{key}_single", f"Raw Speed · {winner['label']}: Single Download", progress_end - 6)
    targets.setdefault(key, {"label": winner["label"], "host": host})["single_down"] = base.iperf_stable(
        host, ports, reverse=True, parallel=1,
        duration=base.IPERF_SINGLE_DURATION, max_tries=full_tries,
    )
    base.progress(f"raw_{key}_up", f"Raw Speed · {winner['label']}: Multi Upload", progress_end - 3)
    targets[key]["multi_up"] = base.iperf_stable(
        host, ports, reverse=False, parallel=base.IPERF_PARALLEL,
        duration=base.IPERF_DURATION, max_tries=full_tries,
    )

    def best(path):
        vals = [float(item[path]["mbps"]) for item in targets.values() if item.get(path, {}).get("mbps") is not None]
        return round(max(vals), 2) if vals else None

    iperf_download = best("multi_down")
    http_fallback = []
    download_source = "iperf3_reverse"
    download_mbps = iperf_download
    if iperf_download is None or iperf_download < SMART_HTTP_FALLBACK_MBPS:
        base.progress("raw_http_fallback", "Raw Speed · HTTPS-Gegenprobe für verdächtig langsamen iPerf-Download", progress_end - 1)
        for target in HTTP_DOWNLOAD_TARGETS:
            http_fallback.append(_http_download_once(target))
        http_download = _best_http_download(http_fallback)
        if http_download is not None and (download_mbps is None or http_download > download_mbps):
            download_mbps = http_download
            download_source = "https_fallback"

    return {
        "download_mbps": download_mbps,
        "upload_mbps": best("multi_up"),
        "single_download_mbps": best("single_down"),
        "targets": targets,
        "benchmark_mode": base.BENCHMARK_MODE,
        "selected_target": winner["key"],
        "selected_targets": selected_keys,
        "precheck": precheck,
        "http_download_fallback": http_fallback,
        "download_source": download_source,
        "iperf_download_mbps": iperf_download,
        "aggregation": "download validated across two prequalified iPerf networks with HTTPS fallback for suspicious reverse-mode results; upload/single-stream measured on the winning iPerf network",
    }


def _peer_once(endpoint, reverse=False):
    result = base.iperf_once(
        endpoint["host"], endpoint["ports"], reverse=reverse,
        parallel=base.PEER_PARALLEL,
        duration=base.PEER_DURATION,
        max_tries=1 if SMART else max(3, base.PEER_MAX_TRIES),
    )
    result["target_label"] = endpoint["label"]
    return result


def _repeat_single_endpoint(endpoint, reverse):
    samples = []
    count = 2 if SMART else 3
    for _ in range(count):
        samples.append(_peer_once(endpoint, reverse=reverse))
    valid = [x for x in samples if x.get("ok") and x.get("mbps") is not None]
    if not valid:
        failed = dict(samples[-1])
        failed["samples"] = samples
        return failed
    median = statistics.median(float(x["mbps"]) for x in valid)
    chosen = min(valid, key=lambda x: abs(float(x["mbps"]) - median))
    result = dict(chosen)
    result["mbps"] = round(median, 2)
    result["samples"] = samples
    result["sample_count"] = len(valid)
    return result


def iperf_region_direction(region, reverse=False):
    primary = region["primary"]
    secondary = region.get("secondary")
    attempts = []

    first = _peer_once(primary, reverse=reverse)
    attempts.append(first)

    first_value = float(first.get("mbps") or 0.0) if first.get("ok") else 0.0
    should_try_secondary = bool(secondary) and (
        not SMART or not first.get("ok") or first_value < SMART_PEER_FALLBACK_MBPS
    )

    if should_try_secondary:
        attempts.append(_peer_once(secondary, reverse=reverse))

    valid = [x for x in attempts if x.get("ok") and x.get("mbps") is not None]
    if valid:
        chosen = max(valid, key=lambda x: float(x["mbps"]))
        result = dict(chosen)
        result["attempts"] = attempts
        result["selection"] = "best checked regional endpoint"
        return result

    if secondary is None:
        result = _repeat_single_endpoint(primary, reverse)
        result["attempts"] = attempts + result.get("samples", [])
        return result

    failed = dict(attempts[-1]) if attempts else {"ok": False, "mbps": None, "error": "No peer endpoint configured"}
    failed["attempts"] = attempts
    return failed


def peer_region_probe(region):
    primary = region["primary"]
    secondary = region.get("secondary")
    ping_inputs = [(primary["host"], base.PEER_PING_COUNT)]
    if secondary:
        ping_inputs.append((secondary["host"], max(3, base.PEER_PING_COUNT - 1)))
    ping_results = base.parallel_pings(ping_inputs)
    networks = [{"label": primary["label"], "host": primary["host"], "role": "primary", "ping": ping_results[0]}]
    if secondary:
        networks.append({"label": secondary["label"], "host": secondary["host"], "role": "secondary", "ping": ping_results[1]})
    down = iperf_region_direction(region, reverse=True)
    up = iperf_region_direction(region, reverse=False)
    aggregate = robust_aggregate_ping(ping_results)
    trustworthy = _reverse_download_trustworthy(down.get("mbps"), up.get("mbps"))
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
        "download_trustworthy": trustworthy,
        "download_note": None if trustworthy else "Reverse-mode public iPerf result is inconsistent with healthy upload and is excluded from peer scoring.",
        "ping_ms": aggregate.get("avg_ms"),
        "jitter_ms": aggregate.get("jitter_ms"),
        "loss_pct": aggregate.get("loss_pct"),
        "networks": networks,
    }


def peer_connectivity_suite(progress_start=67, progress_end=91):
    regions = {}
    span = (progress_end - progress_start) / max(len(base.PEER_REGIONS), 1)
    for idx, region in enumerate(base.PEER_REGIONS):
        pct = progress_start + idx * span
        base.progress(f"peer_{region['code'].lower()}", f"EU Peer · {region['code']} {region['city']} wird geprüft", pct, {"region": region["code"]})
        result = peer_region_probe(region)
        regions[region["code"]] = result
        base.progress(f"peer_{region['code'].lower()}_done", f"EU Peer · {region['code']} abgeschlossen", pct + span * 0.9, {"region": region["code"], "download_mbps": result.get("download_mbps"), "upload_mbps": result.get("upload_mbps"), "download_trustworthy": result.get("download_trustworthy"), "ping_ms": result.get("ping_ms"), "loss_pct": result.get("loss_pct")})
    return {
        "regions": regions,
        "target_order": [r["code"] for r in base.PEER_REGIONS],
        "method": "short multi-network iPerf3 + ICMP probes; suspicious reverse-mode public iPerf download values are retained for diagnostics but excluded from scoring when contradicted by healthy upload",
        "benchmark_mode": base.BENCHMARK_MODE,
    }


def main():
    if SMART:
        base.IPERF_CONNECT_TIMEOUT_MS = min(base.IPERF_CONNECT_TIMEOUT_MS, 1200)
    base.RAW_TARGETS = RAW_TARGETS
    base.ping_stats = reliable_ping_stats
    base.aggregate_ping = robust_aggregate_ping
    base.dns_test = reliable_dns_test
    base.raw_throughput_suite = raw_throughput_suite
    base.peer_region_probe = peer_region_probe
    base.peer_connectivity_suite = peer_connectivity_suite
    base.iperf_region_direction = iperf_region_direction
    base.main()
