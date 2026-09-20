from flask import g

import app as app_module
import server as server_module
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
