import json
from types import SimpleNamespace

import worker


def _result(sender_mbps, receiver_mbps=None):
    end = {
        "sum_sent": {
            "bits_per_second": sender_mbps * 1_000_000,
            "retransmits": 3,
        },
        "sum_received": {},
    }
    if receiver_mbps is not None:
        end["sum_received"]["bits_per_second"] = receiver_mbps * 1_000_000
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"end": end}),
        stderr="",
    )


def test_upload_uses_remote_receiver_rate_not_buffered_sender_rate(monkeypatch):
    monkeypatch.setattr(
        worker.worker_base,
        "run",
        lambda *args, **kwargs: _result(sender_mbps=252.7, receiver_mbps=196.02),
    )

    result = worker._receiver_iperf_once(
        "example.test", [5201], reverse=False, parallel=4, duration=7, max_tries=1
    )

    assert result["ok"] is True
    assert result["mbps"] == 196.02
    assert result["receiver_mbps"] == 196.02
    assert result["sender_mbps"] == 252.7
    assert result["sender_receiver_delta_pct"] > 28
    assert result["measurement_source"] == "receiver"


def test_reverse_download_also_uses_receiver_confirmed_rate(monkeypatch):
    monkeypatch.setattr(
        worker.worker_base,
        "run",
        lambda *args, **kwargs: _result(sender_mbps=438.0, receiver_mbps=432.3),
    )

    result = worker._receiver_iperf_once(
        "example.test", [5201], reverse=True, parallel=4, duration=7, max_tries=1
    )

    assert result["ok"] is True
    assert result["mbps"] == 432.3
    assert result["measurement_source"] == "receiver"


def test_sender_only_result_is_rejected_instead_of_inflating_speed(monkeypatch):
    monkeypatch.setattr(
        worker.worker_base,
        "run",
        lambda *args, **kwargs: _result(sender_mbps=260.0, receiver_mbps=None),
    )

    result = worker._receiver_iperf_once(
        "example.test", [5201], reverse=False, parallel=4, duration=7, max_tries=1
    )

    assert result["ok"] is False
    assert result["mbps"] is None
    assert "no receiver bitrate" in result["error"]
