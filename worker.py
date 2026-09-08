import json
import os
import random
import subprocess
import time
from pathlib import Path

from config_security import validate_config_path
import worker_v2 as worker_base
from worker_reliable import main


def _receiver_iperf_once(host, ports, reverse=False, parallel=4, duration=15, max_tries=None):
    """Run TCP iPerf3 and use receiver-confirmed throughput.

    iPerf3's sender-side sum_sent can temporarily exceed the real WAN rate on
    short, parallel tests because data accepted into TCP socket buffers has not
    necessarily reached the remote receiver when the test timer stops. Using
    sum_received makes upload and download results reflect bytes that actually
    arrived at the receiving endpoint.
    """
    tries = int(max_tries or worker_base.IPERF_MAX_TRIES)
    candidates = list(ports or [5201])
    random.shuffle(candidates)
    candidates = candidates[:tries]
    errors = []

    for port in candidates:
        cmd = [
            "iperf3",
            "-c",
            host,
            "-4",
            "-p",
            str(port),
            "--connect-timeout",
            str(worker_base.IPERF_CONNECT_TIMEOUT_MS),
            "-P",
            str(parallel),
            "-t",
            str(duration),
            "-J",
        ]
        if reverse:
            cmd.append("-R")

        try:
            proc = worker_base.run(
                cmd,
                timeout=duration + (6 if worker_base.BENCHMARK_MODE == "smart" else 10),
            )
        except subprocess.TimeoutExpired:
            errors.append(f"{port}: timeout")
            continue

        if proc.returncode != 0:
            errors.append(
                f"{port}: {(proc.stderr or proc.stdout).strip().replace(chr(10), ' ')[-160:]}"
            )
            continue

        try:
            data = json.loads(proc.stdout)
        except Exception:
            errors.append(f"{port}: invalid JSON")
            continue

        if data.get("error"):
            errors.append(f"{port}: {data['error']}")
            continue

        end = data.get("end", {})
        received = end.get("sum_received") or {}
        sent = end.get("sum_sent") or {}
        receiver_bps = received.get("bits_per_second")
        sender_bps = sent.get("bits_per_second")

        try:
            receiver_bps = float(receiver_bps)
        except (TypeError, ValueError):
            receiver_bps = 0.0

        if receiver_bps <= 0:
            errors.append(f"{port}: no receiver bitrate")
            continue

        try:
            sender_bps = float(sender_bps)
        except (TypeError, ValueError):
            sender_bps = None

        receiver_mbps = round(receiver_bps / 1_000_000, 2)
        sender_mbps = round(sender_bps / 1_000_000, 2) if sender_bps is not None else None
        delta_pct = None
        if sender_bps is not None and receiver_bps > 0:
            delta_pct = round((sender_bps - receiver_bps) * 100.0 / receiver_bps, 2)

        return {
            "ok": True,
            "host": host,
            "port": port,
            "parallel": parallel,
            "seconds": duration,
            "mbps": receiver_mbps,
            "measurement_source": "receiver",
            "receiver_mbps": receiver_mbps,
            "sender_mbps": sender_mbps,
            "sender_receiver_delta_pct": delta_pct,
            "retransmits": sent.get("retransmits"),
        }

    return {
        "ok": False,
        "host": host,
        "parallel": parallel,
        "seconds": duration,
        "mbps": None,
        "measurement_source": "receiver",
        "error": " | ".join(errors[-3:]) or "No reachable iPerf3 port",
    }


# worker_reliable and worker_v2 share the same imported worker_v2 module.
# Replacing the function here therefore fixes raw-speed, EU-peer and DIRECT
# baseline measurements without duplicating the surrounding benchmark logic.
worker_base.iperf_once = _receiver_iperf_once


def validate_runtime_config():
    kind = os.environ.get("VPN_TYPE", "auto").lower()
    if kind == "none":
        return True

    cfg = Path(os.environ.get("VPN_CONFIG", "/vpn/config"))
    if kind not in {"wireguard", "openvpn"}:
        kind = "openvpn" if cfg.suffix.lower() == ".ovpn" else "wireguard"

    error = validate_config_path(cfg, kind)
    if not error:
        return True

    now = int(time.time())
    print(
        json.dumps(
            {
                "ok": False,
                "config": cfg.name,
                "type": kind,
                "started_at": now,
                "finished_at": now,
                "duration_s": 0,
                "error": f"Unsichere VPN-Config abgelehnt: {error}",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return False


if __name__ == "__main__" and validate_runtime_config():
    main()
