import math
import re
import statistics

import worker_v2 as base


# Public iPerf servers are shared infrastructure and can be busy. Raw tunnel
# capacity therefore uses several independent networks instead of a single
# Leaseweb target selected only by ICMP latency.
RAW_TARGETS = [
    {"key": "fra_leaseweb", "label": "Leaseweb Frankfurt", "host": "speedtest.fra1.de.leaseweb.net", "ports": list(range(5201, 5211))},
    {"key": "fra_clouvider", "label": "Clouvider Frankfurt", "host": "fra.speedtest.clouvider.net", "ports": list(range(5200, 5210))},
    {"key": "ams_clouvider", "label": "Clouvider Amsterdam", "host": "ams.speedtest.clouvider.net", "ports": list(range(5200, 5210))},
    {"key": "ams_eranium", "label": "Eranium Amsterdam", "host": "iperf-ams-nl.eranium.net", "ports": list(range(5201, 5211))},
]


def reliable_ping_stats(host, count=None):
    # The old 180 ms interval could trigger ICMP rate limiting on public test
    # hosts and produced coarse 12.5/25/50% loss steps with only 8 packets.
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
        # One ICMP endpoint may rate-limit while the VPN path is healthy. The
        # lower observed loss is a better indication of actual reachability.
        "loss_pct": round(min(losses), 2),
        "targets": results,
    }


def _quick_probe(target, reverse):
    return base.iperf_once(
        target["host"],
        target["ports"],
        reverse=reverse,
        parallel=2,
        duration=2,
        max_tries=max(3, base.IPERF_MAX_TRIES),
    )


def _probe_score(down, up):
    d = float(down.get("mbps") or 0.0) if down.get("ok") else 0.0
    u = float(up.get("mbps") or 0.0) if up.get("ok") else 0.0
    if d <= 0 and u <= 0:
        return 0.0
    if d <= 0:
        return u * 0.35
    if u <= 0:
        return d * 0.65
    return math.sqrt(d * u)


def raw_throughput_suite(progress_start=31, progress_end=66):
    precheck = []
    base.progress("raw_precheck", "Raw Speed · unabhängige Testnetze werden vorgeprüft", progress_start)

    for target in RAW_TARGETS:
        down = _quick_probe(target, reverse=True)
        up = _quick_probe(target, reverse=False)
        precheck.append({
            "key": target["key"],
            "label": target["label"],
            "host": target["host"],
            "download": down,
            "upload": up,
            "score": round(_probe_score(down, up), 2),
        })

    healthy = sorted((row for row in precheck if row["score"] > 0), key=lambda row: row["score"], reverse=True)
    selected_keys = [row["key"] for row in healthy[:2]]
    if not selected_keys:
        selected_keys = [RAW_TARGETS[0]["key"]]
    selected = [target for target in RAW_TARGETS if target["key"] in selected_keys]

    targets = {}
    span = (progress_end - progress_start) / max(len(selected), 1)
    for idx, target in enumerate(selected):
        base_pct = progress_start + idx * span
        key, host, ports = target["key"], target["host"], target["ports"]
        targets[key] = {"label": target["label"], "host": host}
        base.progress(f"raw_{key}_single", f"Raw Speed · {target['label']}: Single Download", base_pct + 1)
        targets[key]["single_down"] = base.iperf_stable(host, ports, reverse=True, parallel=1, duration=base.IPERF_SINGLE_DURATION, max_tries=max(3, base.IPERF_MAX_TRIES))
        base.progress(f"raw_{key}_down", f"Raw Speed · {target['label']}: Multi Download", base_pct + span * 0.34)
        targets[key]["multi_down"] = base.iperf_stable(host, ports, reverse=True, parallel=base.IPERF_PARALLEL, duration=base.IPERF_DURATION, max_tries=max(3, base.IPERF_MAX_TRIES))
        base.progress(f"raw_{key}_up", f"Raw Speed · {target['label']}: Multi Upload", base_pct + span * 0.7)
        targets[key]["multi_up"] = base.iperf_stable(host, ports, reverse=False, parallel=base.IPERF_PARALLEL, duration=base.IPERF_DURATION, max_tries=max(3, base.IPERF_MAX_TRIES))

    def best(path):
        vals = [float(item[path]["mbps"]) for item in targets.values() if item.get(path, {}).get("mbps") is not None]
        return round(max(vals), 2) if vals else None

    return {
        "download_mbps": best("multi_down"),
        "upload_mbps": best("multi_up"),
        "single_download_mbps": best("single_down"),
        "targets": targets,
        "benchmark_mode": base.BENCHMARK_MODE,
        "selected_target": selected_keys[0] if selected_keys else None,
        "selected_targets": selected_keys,
        "precheck": precheck,
        "aggregation": "best result from two independently prequalified networks",
    }


def _repeat_single_endpoint(endpoint, reverse):
    samples = []
    for _ in range(3):
        result = base.iperf_once(
            endpoint["host"], endpoint["ports"], reverse=reverse,
            parallel=base.PEER_PARALLEL, duration=base.PEER_DURATION,
            max_tries=max(3, base.PEER_MAX_TRIES),
        )
        result["target_label"] = endpoint["label"]
        samples.append(result)
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
    endpoints = [region["primary"]]
    if region.get("secondary"):
        endpoints.append(region["secondary"])

    attempts = []
    for endpoint in endpoints:
        result = base.iperf_once(
            endpoint["host"], endpoint["ports"], reverse=reverse,
            parallel=base.PEER_PARALLEL, duration=base.PEER_DURATION,
            max_tries=max(3, base.PEER_MAX_TRIES),
        )
        result["target_label"] = endpoint["label"]
        attempts.append(result)

    valid = [x for x in attempts if x.get("ok") and x.get("mbps") is not None]
    if valid:
        # A public iPerf endpoint being busy is not a VPN peering failure. Use
        # the best independently hosted endpoint in the region and retain all
        # attempts for diagnostics.
        chosen = max(valid, key=lambda x: float(x["mbps"]))
        result = dict(chosen)
        result["attempts"] = attempts
        result["selection"] = "best independent regional endpoint"
        return result

    # Regions with only one public endpoint get three attempts before being
    # accepted as genuinely unavailable/slow.
    if len(endpoints) == 1:
        result = _repeat_single_endpoint(endpoints[0], reverse)
        result["attempts"] = attempts + result.get("samples", [])
        return result

    failed = dict(attempts[-1]) if attempts else {"ok": False, "mbps": None, "error": "No peer endpoint configured"}
    failed["attempts"] = attempts
    return failed


def main():
    base.RAW_TARGETS = RAW_TARGETS
    base.ping_stats = reliable_ping_stats
    base.aggregate_ping = robust_aggregate_ping
    base.raw_throughput_suite = raw_throughput_suite
    base.iperf_region_direction = iperf_region_direction
    base.main()
