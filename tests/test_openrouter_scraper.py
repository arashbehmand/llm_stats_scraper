from datetime import datetime, timedelta, timezone

from scrapers.openrouter import scrape_openrouter


class _FakeResponse:
    def __init__(self, text="", json_data=None):
        self.text = text
        self._json_data = json_data

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_data


def _make_fake_get(model_catalog, seen_urls):
    def _fake_get(url, headers=None, timeout=None):
        seen_urls.append(url)
        if "frontend/models" in url:
            return _FakeResponse(json_data=model_catalog)
        if "rankings" in url:
            return _FakeResponse('<script src="/ranking-chunk.js"></script>')
        if url.endswith("/ranking-chunk.js"):
            return _FakeResponse(
                '(0,l.createServerReference)("deadbeef",x,void 0,y,'
                '"getModelRankingsCached")'
            )
        return _FakeResponse("")

    return _fake_get


def test_scrape_openrouter_returns_only_recent_visible_listings(monkeypatch):
    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    old_ts = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    catalog = {
        "data": [
            {
                "slug": "labs/stealth-model",
                "permaslug": "labs/stealth-model-20260309",
                "name": "Labs: Stealth Model",
                "created_at": recent_ts,
                "hidden": False,
            },
            {
                "slug": "labs/old-model",
                "permaslug": "labs/old-model-20260301",
                "name": "Labs: Old Model",
                "created_at": old_ts,
                "hidden": False,
            },
            {
                "slug": "labs/hidden-model",
                "permaslug": "labs/hidden-model-20260309",
                "name": "Labs: Hidden Model",
                "created_at": recent_ts,
                "hidden": True,
            },
        ]
    }
    seen_urls = []
    posts = []

    monkeypatch.setattr(
        "scrapers.openrouter.requests.get",
        _make_fake_get(catalog, seen_urls),
    )
    monkeypatch.setattr(
        "scrapers.openrouter.requests.post",
        lambda *args, **kwargs: posts.append(args) or _FakeResponse(),
    )

    rows = scrape_openrouter()

    assert [row["model"] for row in rows] == ["Labs: Stealth Model"]
    assert rows[0]["source"] == "openrouter_new"
    assert rows[0]["rank"] is None
    assert rows[0]["details"]["is_new_listing"] is True
    assert rows[0]["details"]["usage_metric_key"] == "new_listing"
    assert posts == []
    assert all("rankings" not in url for url in seen_urls)


def test_scrape_openrouter_returns_empty_when_no_recent_listings(monkeypatch):
    old_ts = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    catalog = {
        "data": [
            {
                "slug": "labs/old-model",
                "permaslug": "labs/old-model-20260301",
                "name": "Labs: Old Model",
                "createdAt": old_ts,
                "hidden": False,
            }
        ]
    }
    seen_urls = []

    monkeypatch.setattr(
        "scrapers.openrouter.requests.get",
        _make_fake_get(catalog, seen_urls),
    )

    rows = scrape_openrouter()

    assert rows == []
    assert all("rankings" not in url for url in seen_urls)
