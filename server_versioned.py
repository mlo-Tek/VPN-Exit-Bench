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

    if "version-status.css" not in html:
        html = html.replace(
            "</head>",
            '<link rel="stylesheet" href="/static/version-status.css">\n</head>',
            1,
        )
    if "version-status.js" not in html:
        html = html.replace(
            "</body>",
            '<script src="/static/version-status.js"></script>\n</body>',
            1,
        )
    return html


app.view_functions["index"] = index_with_version_status
