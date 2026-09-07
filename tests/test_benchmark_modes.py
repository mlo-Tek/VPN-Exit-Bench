import json

import worker_v2


def test_smart_mode_is_default_and_shorter_than_deep():
    assert worker_v2.BENCHMARK_MODE == "smart"
    assert worker_v2.IPERF_DURATION == 7
    assert worker_v2.IPERF_SINGLE_DURATION == 4
    assert worker_v2.PEER_DURATION == 2
    assert worker_v2.PING_COUNT == 8


def test_smart_raw_speed_selects_best_precheck_target(monkeypatch):
    def fake_pings(items):
        assert len(items) == 2
        return [
            {"avg_ms": 22.0, "loss_pct": 0.0},
            {"avg_ms": 13.0, "loss_pct": 0.0},
        ]

    def fake_iperf(host, ports, reverse=False, parallel=4, duration=15, max_tries=None):
        return {"ok": True, "host": host, "mbps": 400.0 if reverse else 180.0}

    monkeypatch.setattr(worker_v2, "parallel_pings", fake_pings)
    monkeypatch.setattr(worker_v2, "iperf_once", fake_iperf)
    monkeypatch.setattr(worker_v2, "progress", lambda *args, **kwargs: None)

    result = worker_v2.raw_throughput_suite()
    assert result["selected_target"] == "ams"
    assert list(result["targets"]) == ["ams"]


def test_peer_iperf_falls_back_to_secondary_without_circular_payload(monkeypatch):
    region = worker_v2.PEER_REGIONS[0]

    def fake_iperf(host, ports, reverse=False, parallel=4, duration=15, max_tries=None):
        if host == region["primary"]["host"]:
            return {"ok": False, "host": host, "mbps": None, "error": "primary unavailable"}
        return {"ok": True, "host": host, "mbps": 123.4}

    monkeypatch.setattr(worker_v2, "iperf_once", fake_iperf)
    result = worker_v2.iperf_region_direction(region, reverse=True)

    assert result["ok"] is True
    assert result["target_label"] == region["secondary"]["label"]
    assert len(result["attempts"]) == 2
    json.dumps(result)


def test_suspicious_low_iperf_is_rechecked_and_medianed(monkeypatch):
    values = iter([1.8, 205.0, 198.0])
    calls = []

    def fake_iperf(*args, **kwargs):
        value = next(values)
        calls.append(value)
        return {"ok": True, "host": "test", "mbps": value}

    monkeypatch.setattr(worker_v2, "iperf_once", fake_iperf)
    result = worker_v2.iperf_stable("test", [5201])

    assert calls == [1.8, 205.0, 198.0]
    assert result["outlier_rechecked"] is True
    assert result["sample_count"] == 3
    assert result["mbps"] == 198.0
    assert result["median_mbps"] == 198.0
    assert len(result["samples"]) == 3


def test_normal_iperf_result_is_not_repeated(monkeypatch):
    calls = []

    def fake_iperf(*args, **kwargs):
        calls.append(1)
        return {"ok": True, "host": "test", "mbps": 150.0}

    monkeypatch.setattr(worker_v2, "iperf_once", fake_iperf)
    result = worker_v2.iperf_stable("test", [5201])

    assert len(calls) == 1
    assert result["mbps"] == 150.0
    assert "outlier_rechecked" not in result


def test_persistently_slow_path_remains_slow_after_median(monkeypatch):
    values = iter([1.1, 1.6, 1.3])

    def fake_iperf(*args, **kwargs):
        return {"ok": True, "host": "test", "mbps": next(values)}

    monkeypatch.setattr(worker_v2, "iperf_once", fake_iperf)
    result = worker_v2.iperf_stable("test", [5201])

    assert result["outlier_rechecked"] is True
    assert result["mbps"] == 1.3
