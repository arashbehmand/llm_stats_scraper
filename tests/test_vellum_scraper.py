import json

import pytest

from scrapers.vellum import scrape_vellum


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_vellum_extracts_models_from_next_flight_payload(monkeypatch):
    models = [
        {
            "title": "Model Lower",
            "gpqaReasoningNum": 60,
            "numAime2025MathCompetition": 70,
            "provider": {"title": "Lab A"},
        },
        {
            "title": "Model Higher",
            "gpqaReasoningNum": 90,
            "numAime2025MathCompetition": 80,
            "provider": {"title": "Lab B"},
        },
    ]
    flight = f'2f:["$","$L38",null,{{"models":{json.dumps(models)}}}]\n'
    html = f"<script>self.__next_f.push([1,{json.dumps(flight)}])</script>"

    monkeypatch.setattr(
        "scrapers.vellum.requests.get", lambda *_, **__: _FakeResponse(html)
    )

    rows = scrape_vellum()

    assert [row["model"] for row in rows] == ["Model Higher", "Model Lower"]
    assert rows[0]["rank"] == 1
    assert rows[0]["score"] == pytest.approx(85.0)
    assert rows[0]["source"] == "vellum"
    assert rows[0]["details"]["metrics"]["GPQA Diamond"] == 90
