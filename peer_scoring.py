REGION_WEIGHTS = {
    "NL": 25,
    "DE": 25,
    "CH": 20,
    "DK": 10,
    "SE": 10,
    "PL": 5,
    "RO": 5,
}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _ratio_score(value, reference):
    value, reference = _num(value), _num(reference)
    if value is None or reference is None or reference <= 0:
        return None
    return round(100.0 * _clamp(value / reference), 1)


def _latency_score(ms):
    ms = _num(ms)
    if ms is None:
        return None
    if ms <= 15: return 100.0
    if ms <= 25: return 92.0
    if ms <= 40: return 80.0
    if ms <= 60: return 65.0
    if ms <= 90: return 45.0
    if ms <= 120: return 25.0
    if ms <= 160: return 10.0
    return 0.0


def _loss_score(loss):
    loss = _num(loss)
    if loss is None:
        return None
    if loss <= 0.0: return 100.0
    if loss <= 0.5: return 95.0
    if loss <= 1.0: return 82.0
    if loss <= 2.0: return 65.0
    if loss <= 5.0: return 30.0
    return 0.0


def _weighted(parts):
    earned = 0.0
    weight = 0.0
    for value, w in parts:
        if value is None:
            continue
        earned += float(value) * float(w)
        weight += float(w)
    return round(earned / weight, 1) if weight else None


def _port_score(status):
    if status == "open": return 100.0
    if status == "mapped_unverified": return 75.0
    if status == "closed": return 0.0
    return 45.0


def _rating(score, port_status):
    if score is None:
        return "Nicht bewertet"
    if port_status == "closed":
        return "Nutzbar – Port geschlossen" if score >= 60 else "Eher ungeeignet"
    suffix = " – Port prüfen" if port_status == "unknown" else ""
    if score >= 90: return "Sehr empfehlenswert" + suffix
    if score >= 78: return "Empfehlenswert" + suffix
    if score >= 65: return "Gut nutzbar" + suffix
    if score >= 50: return "Nutzbar" + suffix
    return "Eher ungeeignet"


def _peer_rating(score):
    if score is None: return "Nicht bewertet"
    if score >= 92: return "Exzellentes EU-Peering"
    if score >= 85: return "Sehr gutes EU-Peering"
    if score >= 75: return "Gutes EU-Peering"
    if score >= 65: return "Solides EU-Peering"
    if score >= 50: return "Durchwachsenes EU-Peering"
    return "Schwaches EU-Peering"


def _region_score(region, reference):
    down = _ratio_score(region.get("download_mbps"), reference.get("down_mbps"))
    up = _ratio_score(region.get("upload_mbps"), reference.get("up_mbps"))
    latency = _latency_score(region.get("ping_ms"))
    loss = _loss_score(region.get("loss_pct"))
    score = _weighted([
        (up, 40),
        (down, 25),
        (latency, 20),
        (loss, 15),
    ])
    result = dict(region)
    result["score"] = score
    result["score_components"] = {
        "upload": up,
        "download": down,
        "latency": latency,
        "stability": loss,
        "weights": {"upload": 40, "download": 25, "latency": 20, "stability": 15},
    }
    return result


def score_payload(payload, reference):
    if not payload.get("ok"):
        payload["torrent_score"] = {"score": 0, "rating": "Fehlgeschlagen", "components": {}}
        return payload

    throughput = payload.get("throughput") or {}
    peer = payload.get("peer_connectivity") or {}
    ping = payload.get("ping") or {}
    pf = payload.get("port_forwarding") or {}
    port_status = pf.get("status", "unknown")

    raw_down = _ratio_score(throughput.get("download_mbps"), reference.get("down_mbps"))
    raw_up = _ratio_score(throughput.get("upload_mbps"), reference.get("up_mbps"))
    raw_speed_score = _weighted([(raw_down, 60), (raw_up, 40)])

    scored_regions = {}
    weighted_region_sum = 0.0
    weighted_region_total = 0.0
    region_scores = []
    for code, region in (peer.get("regions") or {}).items():
        scored = _region_score(region, reference)
        scored_regions[code] = scored
        score = _num(scored.get("score"))
        if score is None:
            continue
        weight = float(REGION_WEIGHTS.get(code, 5))
        weighted_region_sum += score * weight
        weighted_region_total += weight
        region_scores.append(score)

    peer_score = None
    peer_average = None
    peer_worst = None
    if region_scores and weighted_region_total:
        peer_average = round(weighted_region_sum / weighted_region_total, 1)
        peer_worst = round(min(region_scores), 1)
        # The weighted average reflects the likely seedbox/peer pool. A weak
        # single route still matters because torrent swarms are multi-homed.
        peer_score = round(peer_average * 0.85 + peer_worst * 0.15, 1)

    peer["regions"] = scored_regions
    peer["score"] = peer_score
    peer["rating"] = _peer_rating(peer_score)
    peer["average_score"] = peer_average
    peer["worst_region_score"] = peer_worst
    peer["region_weights"] = REGION_WEIGHTS
    peer["weights"] = {"weighted_average": 85, "worst_region": 15}
    peer["core_regions"] = ["NL", "DE", "CH", "DK", "SE"]
    payload["peer_connectivity"] = peer

    stability_score = _weighted([
        (_loss_score(ping.get("loss_pct")), 60),
        (_latency_score(ping.get("avg_ms")), 40),
    ])
    port_score = _port_score(port_status)

    total = _weighted([
        (raw_speed_score, 25),
        (peer_score, 45),
        (port_score, 20),
        (stability_score, 10),
    ])

    payload["speed_score"] = {
        "score": raw_speed_score,
        "download": raw_down,
        "upload": raw_up,
        "reference": reference,
        "weights": {"download": 60, "upload": 40},
    }
    payload["torrent_score"] = {
        "score": total,
        "rating": _rating(total, port_status),
        "port_status": port_status,
        "components": {
            "raw_speed": raw_speed_score,
            "eu_peer": peer_score,
            "port": port_score,
            "stability": stability_score,
            "raw_download": raw_down,
            "raw_upload": raw_up,
        },
        "reference": reference,
        "weights": {"raw_speed": 25, "eu_peer": 45, "port": 20, "stability": 10},
        "model": "torrent-eu-peer-v3",
    }
    return payload
