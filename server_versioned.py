from flask import g

from server import app
from version_info import register_version_route

register_version_route(app)

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
    ]
    scripts = [
        "/static/version-status.js",
        "/static/selection-batch.js",
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
