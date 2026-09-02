from pathlib import Path
import re

from flask import jsonify, request
from werkzeug.utils import secure_filename

import app as app_module
from app import CONFIG_DIR, app, benchmark_active, configs
from peer_scoring import score_payload as score_peer_payload

# app.run_worker resolves score_payload from the app module at runtime. Replace
# the legacy speed-only scorer with the v2 raw-speed + EU-peer scorer without
# duplicating the worker orchestration code.
app_module.score_payload = lambda payload: score_peer_payload(payload, app_module.baseline_reference())

MAX_CONFIG_BYTES = 512 * 1024
ALLOWED_CONFIG_SUFFIXES = {".conf", ".ovpn"}
app.config["MAX_CONTENT_LENGTH"] = max(
    int(app.config.get("MAX_CONTENT_LENGTH") or 0), 4 * 1024 * 1024
)

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
        if len(raw) > MAX_CONFIG_BYTES:
            skipped.append({"name": original_name, "error": "Datei ist größer als 512 KiB."})
            continue
        if not raw.strip():
            skipped.append({"name": original_name, "error": "Datei ist leer."})
            continue
        if b"\x00" in raw:
            skipped.append({"name": original_name, "error": "Binärdateien werden nicht akzeptiert."})
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

    marker = '<div class="card"><div class="row" style="justify-content:space-between"><h2>Configs</h2>'
    if marker in html and "Configs hinzufügen" not in html:
        html = html.replace(marker, UPLOAD_CARD + "\n" + marker, 1)

    head_assets = [
        ("config-upload.css", '<link rel="stylesheet" href="/static/config-upload.css">'),
        ("config-manager.css", '<link rel="stylesheet" href="/static/config-manager.css">'),
    ]
    for needle, tag in head_assets:
        if needle not in html:
            html = html.replace("</head>", tag + "\n</head>", 1)

    body_assets = [
        ("config-upload.js", '<script src="/static/config-upload.js"></script>'),
        ("config-manager.js", '<script src="/static/config-manager.js"></script>'),
    ]
    for needle, tag in body_assets:
        if needle not in html:
            html = html.replace("</body>", tag + "\n</body>", 1)

    return html


app.view_functions["index"] = index_with_config_upload
