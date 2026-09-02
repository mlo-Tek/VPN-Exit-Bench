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

# docker.from_env() falls back to the local Unix socket when DOCKER_HOST is not
# set. Unraid templates can leave the optional proxy variable empty safely.
if not os.environ.get("DOCKER_HOST", "").strip():
    os.environ.pop("DOCKER_HOST", None)

app = Flask(__name__)
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/config/vpns"))
DB_PATH = Path(os.environ.get("DB_PATH", "/config/results.db"))
IMAGE = os.environ.get("WORKER_IMAGE", "ghcr.io/mlo-tek/vpn-exit-bench:latest")
HOST_CONFIG_DIR = os.environ.get("HOST_CONFIG_DIR", "")
REFERENCE_DOWN_MBPS = float(os.environ.get("REFERENCE_DOWN_MBPS", "500"))
REFERENCE_UP_MBPS = float(os.environ.get("REFERENCE_UP_MBPS", "200"))
PROGRESS_PREFIX = "__PROGRESS__"
VALID_BENCHMARK_MODES = {"smart", "deep"}
ACTIVE_JOB_STATES = {"queued", "running", "pausing", "paused", "cancelling"}
TERMINAL_JOB_STATES = {"done", "error", "cancelled"}

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

JOBS = {}
JOBS_LOCK = threading.Lock()
BENCH_LOCK = threading.Lock()
JOB_CONTEXT = threading.local()


def normalize_benchmark_mode(value):
    mode = str(value or "smart").strip().lower()
    return mode if mode in VALID_BENCHMARK_MODES else "smart"


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
            rows.append({"provider": provider, "name": p.name, "rel": str(rel), "type": typ})
    return rows


def resolve_host_config_path(client, rel):
    try:
        this_container = client.containers.get(os.environ.get("HOSTNAME", socket.gethostname()))
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
    row = c.execute("SELECT payload FROM results WHERE provider='baseline' ORDER BY id DESC LIMIT 1").fetchone()
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
            return {"down_mbps": float(down), "up_mbps": float(up), "source": "measured", "ts": baseline.get("finished_at")}
    return {"down_mbps": REFERENCE_DOWN_MBPS, "up_mbps": REFERENCE_UP_MBPS, "source": "configured", "ts": None}


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _label_for_score(score, port_status):
    if port_status == "closed":
        return "Nutzbar – Port geschlossen" if score >= 60 else "Eher ungeeignet"
    if port_status == "unknown":
        if score >= 82: return "Empfehlenswert – Port prüfen"
        if score >= 65: return "Gut nutzbar – Port prüfen"
        if score >= 48: return "Nutzbar – Port prüfen"
        return "Eher ungeeignet"
    if score >= 90: return "Sehr empfehlenswert"
    if score >= 75: return "Empfehlenswert"
    if score >= 60: return "Gut nutzbar"
    if score >= 45: return "Nutzbar"
    return "Eher ungeeignet"


def score_payload(payload):
    if not payload.get("ok"):
        payload["torrent_score"] = {"score": 0, "rating": "Fehlgeschlagen", "components": {}}
        return payload
    tp = payload.get("throughput") or {}
    ping = payload.get("ping") or {}
    pf = payload.get("port_forwarding") or {}
    ref = baseline_reference()
    down, up = tp.get("download_mbps"), tp.get("upload_mbps")
    loss, latency, jitter = ping.get("loss_pct"), ping.get("avg_ms"), ping.get("jitter_ms")
    components, available_weight, earned = {}, 0.0, 0.0
    if down is not None and ref["down_mbps"] > 0:
        value = 35.0 * _clamp(float(down) / ref["down_mbps"]); components["download"] = round(value, 1); available_weight += 35.0; earned += value
    if up is not None and ref["up_mbps"] > 0:
        value = 30.0 * _clamp(float(up) / ref["up_mbps"]); components["upload"] = round(value, 1); available_weight += 30.0; earned += value
    if loss is not None:
        loss = float(loss)
        ratio = 1.0 if loss <= 0.1 else 0.9 if loss <= 0.5 else 0.7 if loss <= 1.0 else 0.4 if loss <= 2.0 else 0.15 if loss <= 5.0 else 0.0
        value = 10.0 * ratio; components["stability"] = round(value, 1); available_weight += 10.0; earned += value
    if latency is not None:
        latency, jitter = float(latency), float(jitter or 0)
        ratio = 1.0 if latency <= 20 else 0.85 if latency <= 35 else 0.7 if latency <= 50 else 0.45 if latency <= 80 else 0.2 if latency <= 120 else 0.0
        if jitter > 20: ratio *= 0.5
        elif jitter > 10: ratio *= 0.75
        elif jitter > 5: ratio *= 0.9
        value = 5.0 * ratio; components["latency"] = round(value, 1); available_weight += 5.0; earned += value
    port_status = pf.get("status", "unknown")
    if port_status != "unknown":
        ratio = 1.0 if port_status == "open" else 0.75 if port_status == "mapped_unverified" else 0.0
        value = 20.0 * ratio; components["port"] = round(value, 1); available_weight += 20.0; earned += value
    score = round((earned / available_weight) * 100, 1) if available_weight else 0.0
    payload["torrent_score"] = {"score": score, "rating": _label_for_score(score, port_status), "port_status": port_status, "components": components, "reference": ref, "weights": {"download": 35, "upload": 30, "port": 20, "stability": 10, "latency": 5}}
    return payload


def store_result(provider, name, typ, payload):
    c = db(); c.execute("INSERT INTO results(ts,provider,name,type,payload) VALUES(?,?,?,?,?)", (int(time.time()), provider, name, typ, json.dumps(payload))); c.commit(); c.close()


def _job_update(job_id, **changes):
    with JOBS_LOCK:
        if job_id in JOBS: JOBS[job_id].update(changes)


def _job_snapshot(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def _job_flag(job_id, key):
    if not job_id:
        return False
    with JOBS_LOCK:
        return bool((JOBS.get(job_id) or {}).get(key))


def _append_job_event(job_id, event):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job: return
        events = job.setdefault("events", []); events.append(event)
        if len(events) > 40: del events[:-40]


def _finish_cancelled(job_id, results=None):
    results = list(results or [])
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(
            status="cancelled",
            pause_requested=False,
            cancel_requested=True,
            worker_percent=0.0,
            phase="Benchmark abgebrochen",
            finished_at=int(time.time()),
            completed=len(results),
            results=results,
        )


def _wait_if_paused(job_id, results):
    while True:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return False
            if job.get("cancel_requested"):
                pass_cancel = True
            else:
                pass_cancel = False
                if not job.get("pause_requested"):
                    if job.get("status") == "paused":
                        job["status"] = "running"
                        job["phase"] = "Benchmark wird fortgesetzt"
                    return True
                job["status"] = "paused"
                job["phase"] = "Benchmark pausiert – Fortsetzen oder Abbrechen"
                job["worker_percent"] = 0.0
        if pass_cancel:
            _finish_cancelled(job_id, results)
            return False
        time.sleep(0.25)


def _handle_worker_progress(job_id, item_index, total_items, config_label, event):
    worker_percent = float(event.get("percent", 0) or 0)
    overall_percent = (((item_index - 1) + worker_percent / 100.0) / max(total_items, 1)) * 100.0
    details = event.get("details") or {}
    normalized = {"config": config_label, "stage": event.get("stage"), "label": event.get("label"), "worker_percent": round(worker_percent, 1), "overall_percent": round(overall_percent, 1), "details": details, "ts": event.get("ts") or int(time.time())}
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job or job.get("status") in {"cancelling", "cancelled"}:
            return
        phase = event.get("label") or ""
        if job.get("pause_requested") and job.get("status") == "pausing":
            phase = f"Pause angefordert · {phase}"
        job.update(percent=round(overall_percent, 1), worker_percent=round(worker_percent, 1), phase=phase, live=details, last_event=normalized)
    stage = event.get("stage") or ""
    if stage.endswith("_done") or stage in {"vpn_connected", "direct", "done", "error"}: _append_job_event(job_id, normalized)


def run_worker(cfg=None, forwarded_port=0, baseline=False, progress_cb=None, mode="smart"):
    client = docker.from_env()
    mode = normalize_benchmark_mode(mode)
    job_id = getattr(JOB_CONTEXT, "job_id", None)
    if job_id and _job_flag(job_id, "cancel_requested"):
        return {"ok": False, "cancelled": True, "benchmark_mode": mode}
    environment = {
        "VPN_TYPE": "none" if baseline else cfg["type"],
        "VPN_PROVIDER": "baseline" if baseline else cfg["provider"],
        "FORWARDED_PORT": str(int(forwarded_port or 0)),
        "BENCHMARK_MODE": mode,
        "IPERF_PARALLEL": "4",
        "PEER_PARALLEL": "2",
    }
    volumes = {}
    if not baseline:
        host_path = resolve_host_config_path(client, cfg["rel"]); volumes[host_path] = {"bind": "/vpn/config", "mode": "ro"}; environment["VPN_CONFIG"] = "/vpn/config"
    container, started, parsed_lines = None, time.time(), 0
    try:
        container = client.containers.run(
            IMAGE,
            command=["python", "worker.py"],
            detach=True,
            cap_drop=["ALL"],
            cap_add=["NET_ADMIN", "NET_RAW", "NET_BIND_SERVICE"],
            security_opt=["no-new-privileges:true"],
            pids_limit=256,
            init=True,
            devices=["/dev/net/tun:/dev/net/tun"],
            volumes=volumes,
            environment=environment,
            labels={"vpn-exit-bench-worker": "1", "vpn-exit-bench-mode": mode, "vpn-exit-bench-job": job_id or "none"},
            network_mode="bridge",
        )
        while True:
            if job_id and _job_flag(job_id, "cancel_requested"):
                try: container.kill()
                except Exception: pass
                return {"ok": False, "cancelled": True, "benchmark_mode": mode}
            try:
                container.reload(); text = container.logs(stdout=True, stderr=True).decode(errors="ignore")
            except Exception:
                text = ""
            lines = text.strip().splitlines() if text.strip() else []
            for line in lines[parsed_lines:]:
                if line.startswith(PROGRESS_PREFIX):
                    try:
                        event = json.loads(line[len(PROGRESS_PREFIX):])
                        if progress_cb: progress_cb(event)
                    except Exception: pass
            parsed_lines = len(lines)
            if getattr(container, "status", "") in {"exited", "dead"}: break
            if time.time() - started > 240:
                try: container.kill()
                except Exception: pass
                raise TimeoutError("Worker benchmark timed out after 240 seconds")
            time.sleep(1)
        try: text = container.logs(stdout=True, stderr=True).decode(errors="ignore")
        except Exception: text = ""
        logs = text.strip().splitlines() if text.strip() else []
        payload = None
        for line in reversed(logs):
            if line.startswith(PROGRESS_PREFIX): continue
            try: payload = json.loads(line); break
            except Exception: pass
        if payload is None: payload = {"ok": False, "error": "Worker returned no JSON", "logs": "\n".join(logs[-30:])}
    except Exception as e:
        payload = {"ok": False, "error": str(e), "benchmark_mode": mode}
    finally:
        if container is not None:
            try: container.remove(force=True)
            except Exception: pass
    return payload if baseline else score_payload(payload)


def run_job(job_id, items, baseline=False, mode="smart"):
    mode = normalize_benchmark_mode(mode)
    with BENCH_LOCK:
        results = []
        JOB_CONTEXT.job_id = job_id
        try:
            if _job_flag(job_id, "cancel_requested"):
                _finish_cancelled(job_id, results)
                return
            if not _wait_if_paused(job_id, results):
                return
            _job_update(job_id, status="running", started_at=int(time.time()), current=0, total=len(items), percent=0.0, worker_percent=0.0, phase=f"{mode.upper()} Benchmark wird vorbereitet", events=[], live={}, benchmark_mode=mode)
            for index, item in enumerate(items, start=1):
                if _job_flag(job_id, "cancel_requested"):
                    _finish_cancelled(job_id, results)
                    return
                if not _wait_if_paused(job_id, results):
                    return
                cfg, port = item.get("config"), item.get("port", 0)
                label = "DIRECT baseline" if baseline else f"{cfg['provider']} / {cfg['name']}"
                _job_update(job_id, current=index, current_label=label, worker_percent=0.0, phase="Worker wird gestartet", live={})
                def progress_cb(event, idx=index, total=len(items), lbl=label): _handle_worker_progress(job_id, idx, total, lbl, event)
                payload = run_worker(cfg=None if baseline else cfg, forwarded_port=port, baseline=baseline, progress_cb=progress_cb, mode=mode)
                if _job_flag(job_id, "cancel_requested") or payload.get("cancelled"):
                    _finish_cancelled(job_id, results)
                    return
                if baseline: store_result("baseline", "DIRECT", "baseline", payload)
                else: store_result(cfg["provider"], cfg["name"], cfg["type"], payload)
                results.append(payload)
                _job_update(job_id, completed=index, percent=round((index / max(len(items), 1)) * 100.0, 1), worker_percent=100.0, phase=f"{label}: gespeichert", results=list(results))
                if index < len(items) and not _wait_if_paused(job_id, results):
                    return
            _job_update(job_id, status="done", percent=100.0, worker_percent=100.0, phase="Benchmark abgeschlossen", finished_at=int(time.time()), completed=len(results), results=results)
        except Exception as e:
            if _job_flag(job_id, "cancel_requested"):
                _finish_cancelled(job_id, results)
            else:
                _job_update(job_id, status="error", error=str(e), phase="Benchmark fehlgeschlagen", finished_at=int(time.time()), completed=len(results), results=results)
        finally:
            JOB_CONTEXT.job_id = None


def create_job(items, baseline=False, mode="smart"):
    mode = normalize_benchmark_mode(mode)
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"id": job_id, "status": "queued", "created_at": int(time.time()), "current": 0, "completed": 0, "total": len(items), "current_label": "", "baseline": baseline, "benchmark_mode": mode, "percent": 0.0, "worker_percent": 0.0, "phase": "Wartet auf freien Benchmark-Slot", "events": [], "live": {}, "pause_requested": False, "cancel_requested": False, "results": []}
    threading.Thread(target=run_job, args=(job_id, items, baseline, mode), daemon=True).start()
    return job_id


def benchmark_active():
    with JOBS_LOCK:
        return any(job.get("status") in ACTIVE_JOB_STATES for job in JOBS.values())


@app.get("/")
def index(): return render_template("index.html")

@app.get("/api/configs")
def api_configs(): return jsonify(configs())

@app.get("/api/baseline")
def api_baseline(): return jsonify({"result": latest_baseline(), "reference": baseline_reference()})

@app.post("/api/baseline")
def start_baseline():
    data = request.get_json(silent=True) or {}
    return jsonify({"job_id": create_job([{}], baseline=True, mode=normalize_benchmark_mode(data.get("mode")))}), 202

@app.get("/api/results")
def results():
    c = db(); cur = c.execute("SELECT id,ts,provider,name,type,payload FROM results WHERE provider != 'baseline' ORDER BY id DESC LIMIT 200"); out = []
    for i, ts, pr, n, t, p in cur:
        x = json.loads(p); x.update({"id": i, "ts": ts, "provider": pr, "name": n, "type": t}); out.append(x)
    c.close(); return jsonify(out)

@app.post("/api/results/clear")
def clear_results():
    if benchmark_active(): return jsonify({"error": "Während eines laufenden Benchmarks können Ergebnisse nicht gelöscht werden."}), 409
    scope = str((request.get_json(silent=True) or {}).get("scope", "vpn")).lower(); c = db(); before = c.total_changes
    if scope == "vpn": c.execute("DELETE FROM results WHERE provider != 'baseline'")
    elif scope == "baseline": c.execute("DELETE FROM results WHERE provider = 'baseline'")
    elif scope == "all": c.execute("DELETE FROM results")
    else: c.close(); return jsonify({"error": "Unknown scope"}), 400
    deleted = c.total_changes - before; c.commit(); c.close(); return jsonify({"ok": True, "deleted": deleted, "scope": scope})

@app.get("/api/jobs/active")
def active_job():
    priority = {"cancelling": 0, "pausing": 1, "running": 2, "paused": 3, "queued": 4}
    with JOBS_LOCK:
        active = [job for job in JOBS.values() if job.get("status") in ACTIVE_JOB_STATES]
        if not active: return jsonify({"job": None})
        active.sort(key=lambda x: (priority.get(x.get("status"), 9), -int(x.get("created_at", 0))))
        return jsonify({"job": dict(active[0])})

@app.get("/api/jobs/<job_id>")
def job_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job: return jsonify({"error": "Unknown job"}), 404
        return jsonify(dict(job))

@app.post("/api/jobs/<job_id>/pause")
def pause_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job: return jsonify({"error": "Unknown job"}), 404
        status = job.get("status")
        if status in TERMINAL_JOB_STATES:
            return jsonify({"error": "Dieser Benchmark ist bereits beendet.", "job": dict(job)}), 409
        job["pause_requested"] = True
        if status == "running":
            job["status"] = "pausing"
            job["phase"] = "Pause angefordert – aktuelle Config wird noch abgeschlossen"
        elif status == "queued":
            job["status"] = "paused"
            job["phase"] = "Benchmark pausiert – noch nicht gestartet"
        return jsonify({"ok": True, "job": dict(job)})

@app.post("/api/jobs/<job_id>/resume")
def resume_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job: return jsonify({"error": "Unknown job"}), 404
        status = job.get("status")
        if status in TERMINAL_JOB_STATES:
            return jsonify({"error": "Dieser Benchmark ist bereits beendet.", "job": dict(job)}), 409
        if status == "cancelling":
            return jsonify({"error": "Der Benchmark wird bereits abgebrochen.", "job": dict(job)}), 409
        job["pause_requested"] = False
        if status in {"paused", "pausing"}:
            job["status"] = "running" if job.get("started_at") else "queued"
            job["phase"] = "Benchmark wird fortgesetzt"
        return jsonify({"ok": True, "job": dict(job)})

@app.post("/api/jobs/<job_id>/cancel")
def cancel_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job: return jsonify({"error": "Unknown job"}), 404
        status = job.get("status")
        if status == "cancelled":
            return jsonify({"ok": True, "job": dict(job)})
        if status in {"done", "error"}:
            return jsonify({"error": "Dieser Benchmark ist bereits beendet.", "job": dict(job)}), 409
        job["cancel_requested"] = True
        job["pause_requested"] = False
        if status in {"queued", "paused"}:
            job.update(status="cancelled", phase="Benchmark abgebrochen", finished_at=int(time.time()), worker_percent=0.0)
            return jsonify({"ok": True, "job": dict(job)})
        job["status"] = "cancelling"
        job["phase"] = "Benchmark wird abgebrochen – aktueller Worker wird beendet"
        return jsonify({"ok": True, "job": dict(job)}), 202

@app.post("/api/test")
def test():
    data = request.get_json(silent=True) or {}
    rel = data.get("rel", "")
    port = int(data.get("port", 0) or 0)
    mode = normalize_benchmark_mode(data.get("mode"))
    allowed = {x["rel"]: x for x in configs()}
    if rel not in allowed: return jsonify({"error": "Unknown config"}), 404
    return jsonify({"job_id": create_job([{"config": allowed[rel], "port": port}], mode=mode)}), 202

@app.post("/api/test-all")
def test_all():
    data = request.get_json(silent=True) or {}
    ports = data.get("ports") or {}
    mode = normalize_benchmark_mode(data.get("mode"))
    items = [{"config": cfg, "port": int(ports.get(cfg["rel"], 0) or 0)} for cfg in configs()]
    if not items: return jsonify({"error": "No configs found"}), 400
    return jsonify({"job_id": create_job(items, mode=mode)}), 202


if __name__ == "__main__": app.run(host="0.0.0.0", port=8787, threaded=True)
