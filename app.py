from flask import Flask, render_template, jsonify, request
import docker
import json
import os
import socket
import sqlite3
import threading
import time
import uuid
from pathlib import Path

app = Flask(__name__)
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/config/vpns"))
DB_PATH = Path(os.environ.get("DB_PATH", "/config/results.db"))
IMAGE = os.environ.get("WORKER_IMAGE", "ghcr.io/mlo-tek/vpn-exit-bench:latest")
HOST_CONFIG_DIR = os.environ.get("HOST_CONFIG_DIR", "")
REFERENCE_DOWN_MBPS = float(os.environ.get("REFERENCE_DOWN_MBPS", "500"))
REFERENCE_UP_MBPS = float(os.environ.get("REFERENCE_UP_MBPS", "200"))

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

JOBS = {}
JOBS_LOCK = threading.Lock()
BENCH_LOCK = threading.Lock()


def db():
    c = sqlite3.connect(DB_PATH)
    c.execute(
        """CREATE TABLE IF NOT EXISTS results(
            id INTEGER PRIMARY KEY,
            ts INTEGER,
            provider TEXT,
            name TEXT,
            type TEXT,
            payload TEXT
        )"""
    )
    return c


def configs():
    rows = []
    for p in sorted(CONFIG_DIR.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".conf", ".ovpn"}:
            rel = p.relative_to(CONFIG_DIR)
            provider = rel.parts[0] if len(rel.parts) > 1 else "Other"
            typ = "openvpn" if p.suffix.lower() == ".ovpn" else "wireguard"
            rows.append(
                {
                    "provider": provider,
                    "name": p.name,
                    "rel": str(rel),
                    "type": typ,
                }
            )
    return rows


def resolve_host_config_path(client, rel):
    """Resolve the real Unraid host path backing /config."""
    try:
        this_container = client.containers.get(
            os.environ.get("HOSTNAME", socket.gethostname())
        )
        for mount in this_container.attrs.get("Mounts", []):
            if mount.get("Destination") == "/config" and mount.get("Source"):
                return str(Path(mount["Source"]) / "vpns" / rel)
    except Exception:
        pass

    if HOST_CONFIG_DIR:
        return str(Path(HOST_CONFIG_DIR) / rel)

    raise RuntimeError("Could not resolve the Unraid host path backing /config")


def latest_baseline():
    c = db()
    row = c.execute(
        """SELECT payload FROM results
           WHERE provider='baseline'
           ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    c.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def baseline_reference():
    baseline = latest_baseline()
    if baseline:
        tp = baseline.get("throughput") or {}
        down = tp.get("download_mbps")
        up = tp.get("upload_mbps")
        if down and up:
            return {
                "down_mbps": float(down),
                "up_mbps": float(up),
                "source": "measured",
                "ts": baseline.get("finished_at"),
            }

    return {
        "down_mbps": REFERENCE_DOWN_MBPS,
        "up_mbps": REFERENCE_UP_MBPS,
        "source": "configured",
        "ts": None,
    }


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _label_for_score(score, port_status):
    if port_status == "closed":
        if score >= 60:
            return "Nutzbar – Port geschlossen"
        return "Eher ungeeignet"

    if port_status == "unknown":
        if score >= 82:
            return "Empfehlenswert – Port prüfen"
        if score >= 65:
            return "Gut nutzbar – Port prüfen"
        if score >= 48:
            return "Nutzbar – Port prüfen"
        return "Eher ungeeignet"

    if score >= 90:
        return "Sehr empfehlenswert"
    if score >= 75:
        return "Empfehlenswert"
    if score >= 60:
        return "Gut nutzbar"
    if score >= 45:
        return "Nutzbar"
    return "Eher ungeeignet"


def score_payload(payload):
    if not payload.get("ok"):
        payload["torrent_score"] = {
            "score": 0,
            "rating": "Fehlgeschlagen",
            "components": {},
        }
        return payload

    tp = payload.get("throughput") or {}
    ping = payload.get("ping") or {}
    pf = payload.get("port_forwarding") or {}
    ref = baseline_reference()

    down = tp.get("download_mbps")
    up = tp.get("upload_mbps")
    loss = ping.get("loss_pct")
    latency = ping.get("avg_ms")
    jitter = ping.get("jitter_ms")

    components = {}
    available_weight = 0.0
    earned = 0.0

    if down is not None and ref["down_mbps"] > 0:
        value = 35.0 * _clamp(float(down) / ref["down_mbps"])
        components["download"] = round(value, 1)
        available_weight += 35.0
        earned += value

    if up is not None and ref["up_mbps"] > 0:
        value = 30.0 * _clamp(float(up) / ref["up_mbps"])
        components["upload"] = round(value, 1)
        available_weight += 30.0
        earned += value

    if loss is not None:
        loss = float(loss)
        if loss <= 0.1:
            ratio = 1.0
        elif loss <= 0.5:
            ratio = 0.9
        elif loss <= 1.0:
            ratio = 0.7
        elif loss <= 2.0:
            ratio = 0.4
        elif loss <= 5.0:
            ratio = 0.15
        else:
            ratio = 0.0
        value = 10.0 * ratio
        components["stability"] = round(value, 1)
        available_weight += 10.0
        earned += value

    if latency is not None:
        latency = float(latency)
        jitter = float(jitter or 0)
        if latency <= 20:
            ratio = 1.0
        elif latency <= 35:
            ratio = 0.85
        elif latency <= 50:
            ratio = 0.7
        elif latency <= 80:
            ratio = 0.45
        elif latency <= 120:
            ratio = 0.2
        else:
            ratio = 0.0

        if jitter > 20:
            ratio *= 0.5
        elif jitter > 10:
            ratio *= 0.75
        elif jitter > 5:
            ratio *= 0.9

        value = 5.0 * ratio
        components["latency"] = round(value, 1)
        available_weight += 5.0
        earned += value

    port_status = pf.get("status", "unknown")
    if port_status != "unknown":
        if port_status == "open":
            ratio = 1.0
        elif port_status == "mapped_unverified":
            ratio = 0.75
        else:
            ratio = 0.0
        value = 20.0 * ratio
        components["port"] = round(value, 1)
        available_weight += 20.0
        earned += value

    score = round((earned / available_weight) * 100, 1) if available_weight else 0.0

    payload["torrent_score"] = {
        "score": score,
        "rating": _label_for_score(score, port_status),
        "port_status": port_status,
        "components": components,
        "reference": ref,
        "weights": {
            "download": 35,
            "upload": 30,
            "port": 20,
            "stability": 10,
            "latency": 5,
        },
    }
    return payload


def store_result(provider, name, typ, payload):
    c = db()
    c.execute(
        "INSERT INTO results(ts,provider,name,type,payload) VALUES(?,?,?,?,?)",
        (
            int(time.time()),
            provider,
            name,
            typ,
            json.dumps(payload),
        ),
    )
    c.commit()
    c.close()


def run_worker(cfg=None, forwarded_port=0, baseline=False):
    client = docker.from_env()
    environment = {
        "VPN_TYPE": "none" if baseline else cfg["type"],
        "VPN_PROVIDER": "baseline" if baseline else cfg["provider"],
        "FORWARDED_PORT": str(int(forwarded_port or 0)),
        "PING_COUNT": "20",
        "IPERF_DURATION": "15",
        "IPERF_SINGLE_DURATION": "8",
        "IPERF_PARALLEL": "4",
    }

    volumes = {}
    if not baseline:
        host_path = resolve_host_config_path(client, cfg["rel"])
        volumes[host_path] = {"bind": "/vpn/config", "mode": "ro"}
        environment["VPN_CONFIG"] = "/vpn/config"

    container = None
    try:
        container = client.containers.run(
            IMAGE,
            command=["python", "worker.py"],
            detach=True,
            cap_add=["NET_ADMIN"],
            devices=["/dev/net/tun:/dev/net/tun"],
            volumes=volumes,
            environment=environment,
            labels={"vpn-exit-bench-worker": "1"},
            network_mode="bridge",
        )
        container.wait(timeout=180)
        logs = (
            container.logs(stdout=True, stderr=True)
            .decode(errors="ignore")
            .strip()
            .splitlines()
        )
        payload = None
        for line in reversed(logs):
            try:
                payload = json.loads(line)
                break
            except Exception:
                pass

        if payload is None:
            payload = {
                "ok": False,
                "error": "Worker returned no JSON",
                "logs": "\n".join(logs[-30:]),
            }
    except Exception as e:
        payload = {"ok": False, "error": str(e)}
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass

    if baseline:
        return payload
    return score_payload(payload)


def _job_update(job_id, **changes):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(changes)


def run_job(job_id, items, baseline=False):
    with BENCH_LOCK:
        _job_update(
            job_id,
            status="running",
            started_at=int(time.time()),
            current=0,
            total=len(items),
        )

        results = []
        try:
            for index, item in enumerate(items, start=1):
                cfg = item.get("config")
                port = item.get("port", 0)
                label = "DIRECT baseline" if baseline else f"{cfg['provider']} / {cfg['name']}"
                _job_update(
                    job_id,
                    current=index,
                    current_label=label,
                )

                payload = run_worker(
                    cfg=None if baseline else cfg,
                    forwarded_port=port,
                    baseline=baseline,
                )

                if baseline:
                    store_result("baseline", "DIRECT", "baseline", payload)
                else:
                    store_result(
                        cfg["provider"],
                        cfg["name"],
                        cfg["type"],
                        payload,
                    )

                results.append(payload)

            _job_update(
                job_id,
                status="done",
                finished_at=int(time.time()),
                results=results,
            )
        except Exception as e:
            _job_update(
                job_id,
                status="error",
                error=str(e),
                finished_at=int(time.time()),
                results=results,
            )


def create_job(items, baseline=False):
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "created_at": int(time.time()),
            "current": 0,
            "total": len(items),
            "current_label": "",
            "baseline": baseline,
        }

    thread = threading.Thread(
        target=run_job,
        args=(job_id, items, baseline),
        daemon=True,
    )
    thread.start()
    return job_id


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/configs")
def api_configs():
    return jsonify(configs())


@app.get("/api/baseline")
def api_baseline():
    baseline = latest_baseline()
    return jsonify(
        {
            "result": baseline,
            "reference": baseline_reference(),
        }
    )


@app.post("/api/baseline")
def start_baseline():
    job_id = create_job([{}], baseline=True)
    return jsonify({"job_id": job_id}), 202


@app.get("/api/results")
def results():
    c = db()
    cur = c.execute(
        """SELECT id,ts,provider,name,type,payload
           FROM results
           WHERE provider != 'baseline'
           ORDER BY id DESC LIMIT 200"""
    )
    out = []
    for i, ts, pr, n, t, p in cur:
        x = json.loads(p)
        x.update(
            {
                "id": i,
                "ts": ts,
                "provider": pr,
                "name": n,
                "type": t,
            }
        )
        out.append(x)
    c.close()
    return jsonify(out)


@app.get("/api/jobs/<job_id>")
def job_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Unknown job"}), 404
        return jsonify(dict(job))


@app.post("/api/test")
def test():
    data = request.get_json(silent=True) or {}
    rel = data.get("rel", "")
    port = int(data.get("port", 0) or 0)

    allowed = {x["rel"]: x for x in configs()}
    if rel not in allowed:
        return jsonify({"error": "Unknown config"}), 404

    job_id = create_job([{"config": allowed[rel], "port": port}])
    return jsonify({"job_id": job_id}), 202


@app.post("/api/test-all")
def test_all():
    data = request.get_json(silent=True) or {}
    ports = data.get("ports") or {}
    items = [
        {
            "config": cfg,
            "port": int(ports.get(cfg["rel"], 0) or 0),
        }
        for cfg in configs()
    ]
    if not items:
        return jsonify({"error": "No configs found"}), 400

    job_id = create_job(items)
    return jsonify({"job_id": job_id}), 202


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787, threaded=True)
