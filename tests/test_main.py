import io
import sys

from main import SCRAPERS, _safe_print


def test_safe_print_does_not_crash_on_cp1252_stdout(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)

    _safe_print("🆕")

    stream.flush()
    assert raw.getvalue().replace(b"\r\n", b"\n") == "🆕\n".encode()


def test_openrouter_registered_as_new_listing_source():
    source_names = [name for name, _func, _args in SCRAPERS]

    assert "openrouter_new" in source_names
    assert "openrouter" not in source_names
