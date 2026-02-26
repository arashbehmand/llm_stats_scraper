from logic.diff import run_diff


def _row(model, rank, score=100.0, details=None):
    return {
        "model": model,
        "rank": rank,
        "score": score,
        "details": details or {},
    }


def test_run_diff_returns_none_without_previous_state():
    current = {"openrouter": [_row("Model A", 1, 1.0)]}
    assert run_diff(current, {}) is None


def test_variant_is_not_treated_as_fully_new_family():
    previous = {"openrouter": [_row("gpt-5.2", 1, 1.0)]}
    current = {
        "openrouter": [
            _row("gpt-5.2", 1, 1.0),
            _row("gpt-5.2-high", 2, 0.9),
        ]
    }

    report = run_diff(current, previous)
    assert report is not None
    assert len(report["new_entries"]) == 1
    entry = report["new_entries"][0]
    assert entry["model"] == "gpt-5.2-high"
    assert entry["entry_type"] == "variant"
    assert entry["variant_of"] == "gpt-5.2"


def test_cascade_rank_drops_are_suppressed():
    previous = {
        "openrouter": [
            _row("A", 1, 1.0),
            _row("B", 2, 0.9),
            _row("C", 3, 0.8),
        ]
    }
    current = {
        "openrouter": [
            _row("X", 1, 0.7),
            _row("A", 2, 1.0),
            _row("B", 3, 0.9),
            _row("C", 4, 0.8),
        ]
    }

    report = run_diff(current, previous)
    assert report is not None
    assert len(report["new_entries"]) == 1
    assert report["new_entries"][0]["model"] == "X"
    assert report["rank_changes"] == []


def test_non_cascade_rank_drop_is_reported():
    previous = {
        "openrouter": [
            _row("A", 1, 1.0),
            _row("B", 2, 0.9),
            _row("C", 3, 0.8),
        ]
    }
    current = {
        "openrouter": [
            _row("X", 1, 0.7),
            _row("A", 2, 1.0),
            _row("B", 5, 0.9),
            _row("C", 3, 0.8),
        ]
    }

    report = run_diff(current, previous)
    assert report is not None
    models = [change["model"] for change in report["rank_changes"]]
    assert "B" in models


def test_lower_table_rank_churn_is_suppressed():
    previous = {"arena_vision": [_row("Old Model", 11, 1200.0)]}
    current = {"arena_vision": [_row("Old Model", 13, 1199.0)]}

    report = run_diff(current, previous)
    assert report is not None
    assert report["rank_changes"] == []


def test_score_change_uses_source_threshold():
    previous = {"openrouter": [_row("A", 1, 1.0)]}
    current = {"openrouter": [_row("A", 1, 1.7)]}

    report = run_diff(current, previous)
    assert report is not None
    assert len(report["score_changes"]) == 1
    change = report["score_changes"][0]
    assert change["model"] == "A"
    assert change["diff"] == 0.7
