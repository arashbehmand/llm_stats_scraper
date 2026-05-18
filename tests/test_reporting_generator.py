from reporting.generator import _build_prompt_signals


def test_build_prompt_signals_uses_mechanical_hints_without_openrouter_usage():
    diff_report = {
        "new_entries": [
            {"source": "arena_text", "model": "New Top", "rank": 1},
        ],
        "rank_changes": [
            {
                "source": "arena_text",
                "model": "Old Top",
                "old_rank": 1,
                "new_rank": 2,
                "change": -1,
            }
        ],
        "score_changes": [],
    }
    current_state = {"arena_text": []}

    signals = _build_prompt_signals(diff_report, current_state)

    assert "mechanical_drop_candidates: arena_text:Old Top" in signals
    assert "openrouter_top_by_usage" not in signals


def test_build_prompt_signals_lists_openrouter_new_listings():
    diff_report = {
        "new_entries": [
            {
                "source": "openrouter_new",
                "model": "Fresh Model",
                "rank": None,
                "details": {"is_new_listing": True},
            }
        ],
        "rank_changes": [],
        "score_changes": [],
    }
    current_state = {
        "openrouter_new": [
            {
                "model": "Fresh Model",
                "rank": None,
                "score": 0.0,
                "details": {"is_new_listing": True},
            }
        ]
    }

    signals = _build_prompt_signals(diff_report, current_state)

    assert "openrouter_new_listings: Fresh Model" in signals
    assert "openrouter_top_by_usage" not in signals
