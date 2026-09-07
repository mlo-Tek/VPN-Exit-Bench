from copy import deepcopy

from peer_scoring import score_payload


REFERENCE = {"down_mbps": 500, "up_mbps": 200}


def _payload(port_status):
    regions = {
        code: {
            "download_mbps": 400,
            "upload_mbps": 160,
            "ping_ms": 25,
            "loss_pct": 0,
        }
        for code in ["NL", "DE", "CH", "DK", "SE", "PL", "RO"]
    }
    return {
        "ok": True,
        "throughput": {"download_mbps": 400, "upload_mbps": 160},
        "peer_connectivity": {"regions": regions},
        "ping": {"avg_ms": 25, "loss_pct": 0},
        "port_forwarding": {"status": port_status},
    }


def test_port_status_does_not_change_torrent_score():
    scores = []
    for status in ["open", "mapped_unverified", "unknown", "closed"]:
        result = score_payload(deepcopy(_payload(status)), REFERENCE)
        scores.append(result["torrent_score"]["score"])
        assert result["torrent_score"]["port_status"] == status
        assert "port" not in result["torrent_score"]["components"]
        assert "port" not in result["torrent_score"]["weights"]

    assert len(set(scores)) == 1


def test_torrent_score_weights_prioritize_peer_and_speed():
    result = score_payload(_payload("unknown"), REFERENCE)
    assert result["torrent_score"]["weights"] == {
        "raw_speed": 40,
        "eu_peer": 50,
        "stability": 10,
    }
    assert result["torrent_score"]["model"] == "torrent-eu-peer-v5-reverse-aware-no-port"
    assert result["torrent_score"]["model_version"] == 5


def test_untrustworthy_reverse_peer_download_is_excluded_from_region_score():
    payload = _payload("unknown")
    payload["peer_connectivity"]["regions"]["DE"].update({
        "download_mbps": 1.1,
        "upload_mbps": 190.0,
        "download_trustworthy": False,
    })

    result = score_payload(payload, REFERENCE)
    de = result["peer_connectivity"]["regions"]["DE"]

    assert de["score_components"]["download"] is None
    assert de["score_components"]["download_trustworthy"] is False
    assert de["score"] > 70
