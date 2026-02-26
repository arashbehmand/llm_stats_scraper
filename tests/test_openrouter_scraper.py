from scrapers.openrouter import scrape_openrouter


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_openrouter_is_sorted_by_usage_value(monkeypatch):
    payload_line = (
        '1:["$",null,null,{"data":[{"name":"Model Low","request_count":10},'
        '{"name":"Model High","request_count":100},'
        '{"name":"Model Mid","request_count":50}]}]'
    )
    fake_text = "\n".join(["header", payload_line, "footer"])

    def _fake_get(url, headers):
        return _FakeResponse(fake_text)

    monkeypatch.setattr("scrapers.openrouter.requests.get", _fake_get)
    rows = scrape_openrouter()

    assert len(rows) == 3
    assert rows[0]["model"] == "Model High"
    assert rows[0]["rank"] == 1
    assert rows[1]["model"] == "Model Mid"
    assert rows[1]["rank"] == 2
    assert rows[2]["model"] == "Model Low"
    assert rows[2]["rank"] == 3
