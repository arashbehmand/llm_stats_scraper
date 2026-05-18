import json

from scrapers.artificial_analysis import scrape_artificial_analysis


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_artificial_analysis_accepts_camelcase_intelligence_index(monkeypatch):
    payload = [
        "$",
        "div",
        None,
        {
            "models": [
                {"name": "Model Lower", "intelligenceIndex": 42.5},
                {"name": "Model Higher", "intelligenceIndex": 84.25},
            ]
        },
    ]
    text = "32:" + json.dumps(payload)

    monkeypatch.setattr(
        "scrapers.artificial_analysis.requests.get",
        lambda *_, **__: _FakeResponse(text),
    )

    rows = scrape_artificial_analysis()

    assert [row["model"] for row in rows] == ["Model Higher", "Model Lower"]
    assert [row["rank"] for row in rows] == [1, 2]
    assert rows[0]["score"] == 84.25
