import version_info


def test_current_build_reports_no_update(monkeypatch):
    monkeypatch.setattr(version_info, "BUILD_SHA", "a" * 40)
    monkeypatch.setattr(version_info, "_latest_main_sha", lambda: ("a" * 40, None))
    payload = version_info.version_payload()
    assert payload["installed"]["short"] == "aaaaaaa"
    assert payload["latest"]["short"] == "aaaaaaa"
    assert payload["update_available"] is False


def test_different_main_commit_reports_update(monkeypatch):
    monkeypatch.setattr(version_info, "BUILD_SHA", "a" * 40)
    monkeypatch.setattr(version_info, "_latest_main_sha", lambda: ("b" * 40, None))
    payload = version_info.version_payload()
    assert payload["update_available"] is True


def test_unknown_build_does_not_claim_update(monkeypatch):
    monkeypatch.setattr(version_info, "BUILD_SHA", "unknown")
    monkeypatch.setattr(version_info, "_latest_main_sha", lambda: ("b" * 40, None))
    payload = version_info.version_payload()
    assert payload["installed"]["sha"] is None
    assert payload["update_available"] is None
