import json

from result_history import build_result_rows


def row(row_id, provider, name, score):
    return (
        row_id,
        1_700_000_000 + row_id,
        provider,
        name,
        "wireguard",
        json.dumps({"ok": True, "torrent_score": {"score": score}}),
    )


def failed_row(row_id, provider, name):
    return (
        row_id,
        1_700_000_000 + row_id,
        provider,
        name,
        "wireguard",
        json.dumps({
            "ok": False,
            "error": "worker failed",
            "torrent_score": {"score": 0, "rating": "Fehlgeschlagen", "components": {}},
        }),
    )


def test_latest_per_config_keeps_untouched_batch_results():
    rows = [
        row(12, "Proton", "de.conf", 91),
        row(11, "Proton", "nl.conf", 93),
        row(10, "Proton", "de.conf", 80),
        row(9, "Proton", "nl.conf", 81),
        row(8, "Proton", "ch.conf", 78),
    ]

    result = build_result_rows(rows)

    assert [item["name"] for item in result] == ["de.conf", "nl.conf", "ch.conf"]
    assert result[0]["id"] == 12
    assert result[1]["id"] == 11
    assert result[2]["id"] == 8
    assert result[0]["history_count"] == 2
    assert result[2]["history_count"] == 1


def test_history_mode_returns_every_run():
    rows = [
        row(3, "Windscribe", "nl.conf", 92),
        row(2, "Windscribe", "nl.conf", 88),
        row(1, "Windscribe", "de.conf", 84),
    ]

    result = build_result_rows(rows, include_history=True)

    assert [item["id"] for item in result] == [3, 2, 1]
    assert result[0]["history_count"] == 2
    assert result[1]["history_count"] == 2
    assert result[2]["history_count"] == 1


def test_historical_other_cryptostorm_rows_are_normalized():
    rows = [
        row(2, "CryptoStorm", "cryptostorm-dusseldorf.conf", 89),
        row(1, "Other", "cryptostorm-dusseldorf.conf", 87),
    ]

    result = build_result_rows(rows)

    assert len(result) == 1
    assert result[0]["provider"] == "CryptoStorm"
    assert result[0]["history_count"] == 2


def test_failed_run_does_not_expose_a_numeric_zero_score():
    result = build_result_rows([
        failed_row(1, "Other", "cryptostorm-berlin.conf"),
    ], include_history=True)

    assert result[0]["provider"] == "CryptoStorm"
    assert result[0]["torrent_score"]["score"] is None
    assert result[0]["torrent_score"]["rating"] == "Fehlgeschlagen"
