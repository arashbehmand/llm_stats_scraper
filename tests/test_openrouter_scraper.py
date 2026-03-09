import json

import pytest

from scrapers.openrouter import scrape_openrouter


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def _make_fake_get(rsc_lines, new_models_json=None):
    """Return a monkeypatch-compatible requests.get that serves RSC + optionally new models API."""
    new_models_json = new_models_json or {"data": []}

    def _fake_get(url, headers=None, timeout=None):
        if "frontend/models" in url:

            class _Resp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return new_models_json

            return _Resp()
        return _FakeResponse("\n".join(rsc_lines))

    return _fake_get


# ---------------------------------------------------------------------------
# Token time-series → ranked entries; request_count-only → rank=None
# ---------------------------------------------------------------------------


def _timeseries_line(last_week_ys, current_week_ys=None):
    """Build an RSC line containing a per-model weekly token time-series."""
    entries = [{"x": "2026-02-23", "ys": last_week_ys}]
    if current_week_ys is not None:
        entries.append({"x": "2026-03-02", "ys": current_week_ys})
    payload = json.dumps(["$", None, None, {"data": entries}])
    return f"10:{payload}"


def _modellist_line(models):
    """Build an RSC line with the per-model request_count list."""
    payload = json.dumps(["$", None, None, {"data": models}])
    return f"20:{payload}"


def test_token_based_models_are_ranked(monkeypatch):
    last_week = {
        "vendor/model-high": 1000,
        "vendor/model-low": 200,
        "Others": 500,
    }
    lines = ["header", _timeseries_line(last_week), "footer"]
    monkeypatch.setattr("scrapers.openrouter.requests.get", _make_fake_get(lines))

    rows = scrape_openrouter()
    ranked = [r for r in rows if r["rank"] is not None]

    assert len(ranked) == 2
    assert ranked[0]["rank"] == 1
    assert ranked[0]["details"]["usage_value"] == 1000
    assert ranked[1]["rank"] == 2
    assert ranked[1]["details"]["usage_value"] == 200


def test_request_count_only_models_are_unranked(monkeypatch):
    """Models that only appear in the request_count list get rank=None."""
    models = [
        {"slug": "vendor/a", "name": "Model A", "request_count": 100},
        {"slug": "vendor/b", "name": "Model B", "request_count": 50},
    ]
    lines = ["header", _modellist_line(models), "footer"]
    monkeypatch.setattr("scrapers.openrouter.requests.get", _make_fake_get(lines))

    rows = scrape_openrouter()
    assert all(r["rank"] is None for r in rows)


def test_current_week_share_pct_is_populated(monkeypatch):
    last_week = {"vendor/model-a": 1000, "Others": 1000}
    current_week = {"vendor/model-a": 300, "Others": 700}
    lines = ["header", _timeseries_line(last_week, current_week), "footer"]
    monkeypatch.setattr("scrapers.openrouter.requests.get", _make_fake_get(lines))

    rows = scrape_openrouter()
    ranked = [r for r in rows if r["rank"] is not None]
    assert len(ranked) == 1
    details = ranked[0]["details"]
    assert details["current_week_tokens"] == 300.0
    # current_week_share_pct = 300 / (300 + 700) * 100 = 30%
    assert details["current_week_share_pct"] == pytest.approx(30.0, rel=1e-3)
    # score (last week share) = 1000 / (1000+1000) * 100 = 50%
    assert ranked[0]["score"] == pytest.approx(50.0, rel=1e-3)


def test_new_listing_appears_as_unranked_entry(monkeypatch):
    from datetime import datetime, timedelta, timezone

    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    new_models_json = {
        "data": [
            {
                "slug": "labs/stealth-model",
                "permaslug": "labs/stealth-model-20260309",
                "name": "Labs: Stealth Model",
                "created_at": recent_ts,
                "hidden": False,
            }
        ]
    }
    lines = ["header", "footer"]  # no RSC data → no ranked models
    monkeypatch.setattr(
        "scrapers.openrouter.requests.get", _make_fake_get(lines, new_models_json)
    )

    rows = scrape_openrouter()
    new_entries = [r for r in rows if r.get("details", {}).get("is_new_listing")]
    assert len(new_entries) == 1
    assert new_entries[0]["rank"] is None
    assert new_entries[0]["model"] == "Labs: Stealth Model"


def test_hidden_new_listing_is_excluded(monkeypatch):
    from datetime import datetime, timedelta, timezone

    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    new_models_json = {
        "data": [
            {
                "slug": "labs/hidden-model",
                "permaslug": "labs/hidden-model-20260309",
                "name": "Labs: Hidden Model",
                "created_at": recent_ts,
                "hidden": True,
            }
        ]
    }
    lines = ["header", "footer"]
    monkeypatch.setattr(
        "scrapers.openrouter.requests.get", _make_fake_get(lines, new_models_json)
    )

    rows = scrape_openrouter()
    assert not any(r.get("details", {}).get("is_new_listing") for r in rows)
