from pathlib import Path
import hmac
import json
import os
import re
import secrets
import sqlite3

from flask import Response, g, jsonify, request
from werkzeug.utils import secure_filename

import app as app_module
from app import CONFIG_DIR, app, benchmark_active, configs
from config_security import ALLOWED_CONFIG_SUFFIXES, MAX_CONFIG_BYTES, validate_config_bytes
from peer_scoring import score_payload as score_peer_payload

# app.run_worker resolves score_payload from the app module at runtime. Replace
# the legacy speed-only scorer with the current raw-speed + EU-peer scorer
# without duplicating the worker orchestration code.
app_module.score_payload = lambda payload: score_peer_payload(payload, app_module.baseline_reference())

app.config["MAX_CONTENT_LENGTH"] = max(
    int(app.config.get("MAX_CONTENT_LENGTH") or 0), 4 * 1024 * 1024
)

AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "").strip()
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")
if bool(AUTH_USERNAME) != bool(AUTH_PASSWORD):
    raise RuntimeError("AUTH_USERNAME and AUTH_PASSWORD must either both be set or both be empty")
AUTH_ENABLED = bool(AUTH_USERNAME and AUTH_PASSWORD)
CSRF_TOKEN = os.environ.get("CSRF_TOKEN", "").strip() or secrets.token_urlsafe(32)
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

UPLOAD_CARD = r'''
  <div class="card config-upload-card">
    <div class="config-upload-head">
      <div>
        <h2>Configs hinzufügen</h2>
        <span class="muted small">.conf / .ovpn</span>
      </div>
    </div>
    <label class="dropzone" id="dropzone" for="configFiles">
      <input id="configFiles" type="file" accept=".conf,.ovpn" multiple>
      <span class="dropzone-icon">＋</span>
      <span class="dropzone-copy"><strong>Dateien hier ablegen</strong><span>oder klicken zum Auswählen</span></span>
    </label>
    <div class="upload-footer">
      <div id="selectedFiles" class="uploadmeta">Keine Dateien ausgewählt.</div>
      <button id="uploadBtn" disabled>Hochladen</button>
    </div>
    <div id="uploadStatus" class="uploadstatus"></div>
  </div>
'''


def _sanitize_result_payload(payload, provider=None):
    """Remove the user's pre-VPN public IP from benchmark data."""
    try:
        clean = json.loads(json.dumps(payload))
    except Exception:
        clean = dict(payload or {})

    clean.pop("ip_before", None)

    # A DIRECT baseline only needs throughput/reference data. Do not retain
    # the user's public IP in its exit object either.
    if str(provider or "").lower() == "baseline":
        exit_info = clean.get("exit")
        if isinstance(exit_info, dict):
            exit_info = dict(exit_info)
            exit_info.pop("ip", None)
            clean["exit"] = exit_info
    return clean


def _scrub_legacy_result_ips():
    """One-time-at-startup cleanup for results written by older versions."""
    try:
        c = app_module.db()
        rows = c.execute("SELECT id,provider,payload FROM results").fetchall()
        for row_id, provider, raw_payload in rows:
            try:
                payload = json.loads(raw_payload)
            except Exception:
                continue
            clean = _sanitize_result_payload(payload, provider)
            if clean != payload:
                c.execute(
                    "UPDATE results SET payload=? WHERE id=?",
                    (json.dumps(clean), row_id),
                )
        c.commit()
        c.close()
    except (sqlite3.Error, OSError, ValueError):
        pass


_original_store_result = app_module.store_result


def _safe_store_result(provider, name, typ, payload):
    return _original_store_result(
        provider,
        name,
        typ,
        _sanitize_result_payload(payload, provider),
    )


app_module.store_result = _safe_store_result

# Sanitize the worker return value as well. This prevents ip_before from
# surviving in the in-memory job result returned by /api/jobs/<id>.
_original_run_worker = app_module.run_worker


def _safe_run_worker(cfg=None, forwarded_port=0, baseline=False, progress_cb=None):
    payload = _original_run_worker(
        cfg=cfg,
        forwarded_port=forwarded_port,
        baseline=baseline,
        progress_cb=progress_cb,
    )
    provider = "baseline" if baseline else (cfg or {}).get("provider")
    return _sanitize_result_payload(payload, provider)


app_module.run_worker = _safe_run_worker

# Live progress used to expose the direct public IP before the VPN connected.
# Keep the verification state, but never send that address to the browser.
_original_progress_handler = app_module._handle_worker_progress


def _safe_progress_handler(job_id, item_index, total_items, config_label, event):
    if isinstance(event, dict) and event.get("stage") == "ip_before_done":
        event = dict(event)
        details = dict(event.get("details") or {})
        had_ip = bool(details.pop("ip", None))
        details["verified"] = had_ip
        event["details"] = details
    return _original_progress_handler(
        job_id, item_index, total_items, config_label, event
    )


app_module._handle_worker_progress = _safe_progress_handler
_scrub_legacy_result_ips()


def _auth_ok():
    if not AUTH_ENABLED:
        return True
    auth = request.authorization
    if not auth:
        return False
    return hmac.compare_digest(auth.username or "", AUTH_USERNAME) and hmac.compare_digest(
        auth.password or "", AUTH_PASSWORD
    )


@app.before_request
def enforce_request_security():
    # A fresh nonce lets the existing inline base UI run without unsafe-inline
    # script execution. Dynamic style attributes are separately constrained.
    g.csp_nonce = secrets.token_urlsafe(18)

    # Health checks deliberately reveal only that the process is alive.
    if request.path == "/api/health":
        return None

    if not _auth_ok():
        return Response(
            "Authentication required\n",
            401,
            {"WWW-Authenticate": 'Basic realm="VPN Exit Bench", charset="UTF-8"'},
        )

    if request.method in MUTATING_METHODS:
        supplied = request.headers.get("X-VPN-Bench-CSRF", "")
        if not supplied or not hmac.compare_digest(supplied, CSRF_TOKEN):
            return jsonify({"error": "CSRF-Prüfung fehlgeschlagen. WebUI neu laden."}), 403
    return None


def safe_provider(value):
    value = (value or "").strip()
    if not value:
        return None
    value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value)
    value = re.sub(r"\s+", " ", value).strip(" ._")
    if not value or value in {".", ".."}:
        return None
    return value[:64]


def infer_provider(filename):
    name = Path(filename).stem.lower()
    rules = [
        (r"(^|[-_. ])proton", "Proton"),
        (r"(^|[-_. ])ovpn", "OVPN"),
        (r"(^|[-_. ])mullvad", "Mullvad"),
        (r"(^|[-_. ])airvpn", "AirVPN"),
        (r"(^|[-_. ])ivpn", "IVPN"),
        (r"(^|[-_. ])windscribe", "Windscribe"),
        (r"(^|[-_. ])surfshark", "Surfshark"),
        (r"(^|[-_. ])nord", "NordVPN"),
        (r"(^|[-_. ])pia|privateinternetaccess", "PIA"),
    ]
    for pattern, provider in rules:
        if re.search(pattern, name):
            return provider
    return "Other"


def save_uploaded_configs(files, provider_override=None, overwrite=False):
    uploaded, skipped = [], []
    for file in files:
        original_name = Path(file.filename or "").name
        filename = secure_filename(original_name)
        suffix = Path(filename).suffix.lower()

        if not filename or suffix not in ALLOWED_CONFIG_SUFFIXES:
            skipped.append({"name": original_name or "(ohne Namen)", "error": "Nur .conf und .ovpn sind erlaubt."})
            continue

        raw = file.read(MAX_CONFIG_BYTES + 1)
        validation_error = validate_config_bytes(raw, suffix)
        if validation_error:
            skipped.append({"name": original_name, "error": validation_error})
            continue

        provider = safe_provider(provider_override or infer_provider(filename)) or "Other"
        provider_dir = CONFIG_DIR / provider
        provider_dir.mkdir(parents=True, exist_ok=True)
        try:
            provider_dir.chmod(0o700)
        except OSError:
            pass

        target = provider_dir / filename
        existed = target.exists()
        if existed and not overwrite:
            skipped.append({"name": original_name, "provider": provider, "error": "Existiert bereits."})
            continue

        try:
            target.write_bytes(raw)
            target.chmod(0o600)
        except Exception as exc:
            skipped.append({"name": original_name, "provider": provider, "error": f"Speichern fehlgeschlagen: {exc}"})
            continue

        uploaded.append({
            "provider": provider,
            "name": filename,
            "rel": str(target.relative_to(CONFIG_DIR)),
            "type": "openvpn" if suffix == ".ovpn" else "wireguard",
            "overwritten": existed,
        })
    return uploaded, skipped


@app.after_request
def add_security_headers(response):
    nonce = getattr(g, "csp_nonce", "")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self'; "
        f"style-src-elem 'self' 'nonce-{nonce}'; "
        "style-src-attr 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    )
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.post("/api/configs/upload")
def upload_configs():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Keine Dateien ausgewählt."}), 400

    provider_raw = request.form.get("provider", "")
    provider_override = safe_provider(provider_raw) if provider_raw.strip() else None
    if provider_raw.strip() and not provider_override:
        return jsonify({"error": "Ungültiger Anbietername."}), 400

    overwrite = str(request.form.get("overwrite", "")).lower() in {"1", "true", "yes", "on"}
    if overwrite and benchmark_active():
        return jsonify({"error": "Während eines laufenden Benchmarks können bestehende Configs nicht überschrieben werden."}), 409

    uploaded, skipped = save_uploaded_configs(files, provider_override, overwrite)
    return jsonify({"ok": bool(uploaded), "uploaded": uploaded, "skipped": skipped, "configs": configs()}), (200 if uploaded else 409)


@app.delete("/api/configs")
def delete_configs():
    if benchmark_active():
        return jsonify({"error": "Während eines laufenden Benchmarks können keine Configs gelöscht werden."}), 409

    data = request.get_json(silent=True) or {}
    rels = data.get("rels") or []
    if not isinstance(rels, list) or not rels:
        return jsonify({"error": "Keine Configs ausgewählt."}), 400

    allowed = {item["rel"]: item for item in configs()}
    deleted, skipped = [], []
    root = CONFIG_DIR.resolve()

    for rel in dict.fromkeys(str(x) for x in rels):
        item = allowed.get(rel)
        if not item:
            skipped.append({"rel": rel, "error": "Config nicht gefunden."})
            continue

        target = (CONFIG_DIR / rel).resolve()
        if target == root or root not in target.parents:
            skipped.append({"rel": rel, "error": "Ungültiger Pfad."})
            continue

        try:
            target.unlink()
            deleted.append(item)
        except FileNotFoundError:
            skipped.append({"rel": rel, "error": "Datei existiert nicht mehr."})
            continue
        except Exception as exc:
            skipped.append({"rel": rel, "error": f"Löschen fehlgeschlagen: {exc}"})
            continue

        parent = target.parent
        while parent != root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    return jsonify({"ok": bool(deleted), "deleted": deleted, "skipped": skipped, "configs": configs()}), (200 if deleted else 409)


@app.errorhandler(413)
def upload_too_large(_error):
    return jsonify({"error": "Upload zu groß. Insgesamt sind maximal 4 MiB erlaubt."}), 413


_original_index = app.view_functions["index"]


def index_with_config_upload():
    html = _original_index()
    if not isinstance(html, str):
        try:
            html = html.get_data(as_text=True)
        except Exception:
            return html

    nonce = getattr(g, "csp_nonce", "")
    html = html.replace("<style>", f'<style nonce="{nonce}">', 1)
    html = html.replace("<script>", f'<script nonce="{nonce}">', 1)
    html = html.replace('onclick="loadResults()"', 'id="refreshResultsBtn"', 1)

    marker = '<div class="card"><div class="row" style="justify-content:space-between"><h2>Configs</h2>'
    if marker in html and "Configs hinzufügen" not in html:
        html = html.replace(marker, UPLOAD_CARD + "\n" + marker, 1)

    csrf_meta = f'<meta name="vpnbench-csrf" content="{CSRF_TOKEN}">'
    if "vpnbench-csrf" not in html:
        html = html.replace("</head>", csrf_meta + "\n</head>", 1)

    head_assets = [
        ("config-upload.css", '<link rel="stylesheet" href="/static/config-upload.css">'),
        ("config-manager.css", '<link rel="stylesheet" href="/static/config-manager.css">'),
    ]
    for needle, tag in head_assets:
        if needle not in html:
            html = html.replace("</head>", tag + "\n</head>", 1)

    body_assets = [
        ("security.js", '<script src="/static/security.js"></script>'),
        ("config-upload.js", '<script src="/static/config-upload.js"></script>'),
        ("config-manager.js", '<script src="/static/config-manager.js"></script>'),
    ]
    for needle, tag in body_assets:
        if needle not in html:
            html = html.replace("</body>", tag + "\n</body>", 1)

    return html


app.view_functions["index"] = index_with_config_upload
