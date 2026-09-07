import json
import os
import threading
import time
import urllib.error
import urllib.request

from flask import jsonify

REPO = "mlo-Tek/VPN-Exit-Bench"
REPO_URL = f"https://github.com/{REPO}"
MAIN_COMMIT_API = f"https://api.github.com/repos/{REPO}/commits/main"
BUILD_SHA = os.environ.get("APP_BUILD_SHA", "unknown").strip().lower() or "unknown"
BUILD_DATE = os.environ.get("APP_BUILD_DATE", "").strip()
_CACHE_TTL = 300
_cache = {"at": 0.0, "sha": None, "error": None}
_lock = threading.Lock()


def _short(sha):
    return sha[:7] if sha and sha != "unknown" else "unknown"


def _latest_main_sha():
    now = time.monotonic()
    with _lock:
        if now - _cache["at"] < _CACHE_TTL and (_cache["sha"] or _cache["error"]):
            return _cache["sha"], _cache["error"]

        req = urllib.request.Request(
            MAIN_COMMIT_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "VPN-Exit-Bench/version-check",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=4) as response:
                payload = json.load(response)
            sha = str(payload.get("sha") or "").strip().lower() or None
            error = None if sha else "GitHub lieferte keinen Commit-Stand."
        except (OSError, ValueError, urllib.error.URLError) as exc:
            sha = None
            error = f"Update-Prüfung nicht erreichbar: {exc.__class__.__name__}"

        _cache.update({"at": now, "sha": sha, "error": error})
        return sha, error


def version_payload():
    latest_sha, error = _latest_main_sha()
    installed_known = BUILD_SHA != "unknown"
    update_available = None
    if installed_known and latest_sha:
        update_available = BUILD_SHA != latest_sha

    return {
        "installed": {
            "sha": BUILD_SHA if installed_known else None,
            "short": _short(BUILD_SHA),
            "label": f"main-{_short(BUILD_SHA)}" if installed_known else "unbekannt",
            "built_at": BUILD_DATE or None,
        },
        "latest": {
            "sha": latest_sha,
            "short": _short(latest_sha),
            "label": f"main-{_short(latest_sha)}" if latest_sha else None,
        },
        "update_available": update_available,
        "error": error,
        "repository": REPO_URL,
        "checked_at": int(time.time()),
    }


def register_version_route(app):
    @app.get("/api/version")
    def api_version():
        return jsonify(version_payload())
