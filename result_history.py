import json

from flask import jsonify, request


def _decode_row(row):
    row_id, ts, provider, name, typ, raw_payload = row
    try:
        payload = json.loads(raw_payload)
    except Exception:
        payload = {"ok": False, "error": "Gespeichertes Ergebnis ist ungültig."}
    payload.update(
        {
            "id": row_id,
            "ts": ts,
            "provider": provider,
            "name": name,
            "type": typ,
        }
    )
    return payload


def build_result_rows(rows, include_history=False, max_configs=200):
    """Return benchmark results without ever deleting historical runs.

    Normal mode returns only the newest run for each config. Historical runs
    stay in SQLite and can be requested with ``?history=1``. This makes batch
    tests and later one-off retests additive instead of making older configs
    disappear from the ranking.
    """
    decoded = [_decode_row(row) for row in rows]

    counts = {}
    for item in decoded:
        key = (item.get("provider"), item.get("name"), item.get("type"))
        counts[key] = counts.get(key, 0) + 1

    if include_history:
        for item in decoded:
            key = (item.get("provider"), item.get("name"), item.get("type"))
            item["history_count"] = counts[key]
        return decoded

    latest = []
    seen = set()
    for item in decoded:
        key = (item.get("provider"), item.get("name"), item.get("type"))
        if key in seen:
            continue
        seen.add(key)
        item["history_count"] = counts[key]
        item["history_available"] = counts[key] > 1
        latest.append(item)
        if len(latest) >= max_configs:
            break
    return latest


def register_result_history(app, db_func):
    """Replace /api/results with an additive latest-per-config view."""

    def results_with_history():
        include_history = str(request.args.get("history", "")).lower() in {
            "1",
            "true",
            "yes",
            "all",
        }

        connection = db_func()
        try:
            # Keep enough history for normal home-server use while preventing
            # an unbounded JSON response if the service has run for years.
            limit = 5000 if include_history else 5000
            rows = connection.execute(
                "SELECT id,ts,provider,name,type,payload "
                "FROM results WHERE provider != 'baseline' "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        return jsonify(build_result_rows(rows, include_history=include_history))

    # app.py already registered the route. Replacing its view function keeps
    # the URL and all callers stable while changing only the result semantics.
    app.view_functions["results"] = results_with_history
