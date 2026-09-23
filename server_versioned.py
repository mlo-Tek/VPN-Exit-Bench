from flask import g

import app as app_module
import server as server_module
from port_forwarding import normalize_manual_forward_result
from provider_identity import canonical_provider, infer_provider
from result_history import register_result_history
from server import app
from version_info import register_version_route


_original_configs = app_module.configs


def configs_with_provider_identity():
    rows = []
    for row in _original_configs():
        item = dict(row)
        item["provider"] = canonical_provider(
            item.get("provider"),
            name=item.get("name"),
            rel=item.get("rel"),
        )
        rows.append(item)
    return rows


# Keep config discovery, uploads and historical result labels on the same
# provider identity rules. Assigning the module globals is intentional: the
# already-registered Flask route functions resolve these names at call time.
app_module.configs = configs_with_provider_identity
server_module.configs = configs_with_provider_identity
server_module.infer_provider = infer_provider


# The worker already normalizes manual port checks, but enforce the requested
# port once more at the server boundary. This prevents a supplied qBit port
# from ever being displayed as "unknown" if an older/cached worker image or an
# unavailable external checker returned an incomplete port_forwarding object.
_original_run_worker = app_module.run_worker


def run_worker_with_manual_port(
    cfg=None,
    forwarded_port=0,
    baseline=False,
    progress_cb=None,
    mode="smart",
):
    payload = _original_run_worker(
        cfg=cfg,
        forwarded_port=forwarded_port,
        baseline=baseline,
        progress_cb=progress_cb,
        mode=mode,
    )
    try:
        requested_port = int(forwarded_port or 0)
    except (TypeError, ValueError):
        requested_port = 0

    if (
        not baseline
        and requested_port > 0
        and isinstance(payload, dict)
        and payload.get("ok")
    ):
        payload = dict(payload)
        payload["requested_forwarded_port"] = requested_port
        payload["port_forwarding"] = normalize_manual_forward_result(
            payload.get("port_forwarding") or {},
            requested_port,
        )
    return payload


app_module.run_worker = run_worker_with_manual_port

register_version_route(app)
register_result_history(app, app_module.db)

_original_index = app.view_functions["index"]


def index_with_version_status():
    html = _original_index()
    if not isinstance(html, str):
        try:
            html = html.get_data(as_text=True)
        except Exception:
            return html

    styles = [
        "/static/version-status.css",
        "/static/selection-stability.css",
        "/static/display-fixes.css",
    ]
    scripts = [
        "/static/version-status.js",
        "/static/selection-batch.js",
        "/static/display-fixes.js",
        "/static/provider-port-sync.js",
    ]

    for asset in styles:
        name = asset.rsplit("/", 1)[-1]
        if name not in html:
            html = html.replace(
                "</head>",
                f'<link rel="stylesheet" href="{asset}">\n</head>',
                1,
            )

    for asset in scripts:
        name = asset.rsplit("/", 1)[-1]
        if name not in html:
            html = html.replace(
                "</body>",
                f'<script src="{asset}"></script>\n</body>',
                1,
            )
    return html


app.view_functions["index"] = index_with_version_status
