import subprocess

import worker_reliable


def test_smart_quick_probe_uses_single_short_attempt(monkeypatch):
    monkeypatch.setattr(worker_reliable, "SMART", True)
    calls = []

    def fake_iperf(*args, **kwargs):
        calls.append(kwargs)
        return {"ok": True, "mbps": 123.0}

    monkeypatch.setattr(worker_reliable.base, "iperf_once", fake_iperf)
    worker_reliable._quick_probe(worker_reliable.RAW_TARGETS[0])

    assert len(calls) == 1
    assert calls[0]["duration"] == 1
    assert calls[0]["max_tries"] == 1
    assert calls[0]["reverse"] is True


def test_smart_peer_skips_secondary_when_primary_is_healthy(monkeypatch):
    monkeypatch.setattr(worker_reliable, "SMART", True)
    calls = []
    region = {
        "primary": {"label": "primary", "host": "p", "ports": [5201]},
        "secondary": {"label": "secondary", "host": "s", "ports": [5201]},
    }

    def fake_once(endpoint, reverse=False):
        calls.append(endpoint["label"])
        return {"ok": True, "mbps": 140.0, "target_label": endpoint["label"]}

    monkeypatch.setattr(worker_reliable, "_peer_once", fake_once)
    result = worker_reliable.iperf_region_direction(region, reverse=True)

    assert calls == ["primary"]
    assert result["mbps"] == 140.0


def test_smart_peer_checks_secondary_when_primary_is_suspicious(monkeypatch):
    monkeypatch.setattr(worker_reliable, "SMART", True)
    calls = []
    region = {
        "primary": {"label": "primary", "host": "p", "ports": [5201]},
        "secondary": {"label": "secondary", "host": "s", "ports": [5201]},
    }

    def fake_once(endpoint, reverse=False):
        calls.append(endpoint["label"])
        value = 25.0 if endpoint["label"] == "primary" else 180.0
        return {"ok": True, "mbps": value, "target_label": endpoint["label"]}

    monkeypatch.setattr(worker_reliable, "_peer_once", fake_once)
    result = worker_reliable.iperf_region_direction(region)

    assert calls == ["primary", "secondary"]
    assert result["mbps"] == 180.0
    assert result["target_label"] == "secondary"


def test_dns_timeout_is_nonfatal(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 5))

    monkeypatch.setattr(worker_reliable.base, "run", timeout)
    result = worker_reliable.reliable_dns_test()

    assert result["ok"] is False
    assert "timed out" in result["error"].lower()


def test_reverse_download_is_untrusted_when_upload_is_healthy():
    assert worker_reliable._reverse_download_trustworthy(1.1, 190.0) is False
    assert worker_reliable._reverse_download_trustworthy(70.0, 190.0) is True
    assert worker_reliable._reverse_download_trustworthy(1.1, 30.0) is True


def test_best_http_download_uses_fastest_valid_result():
    results = [
        {"ok": True, "mbps": 120.0},
        {"ok": False, "mbps": None},
        {"ok": True, "mbps": 410.5},
    ]
    assert worker_reliable._best_http_download(results) == 410.5
