from reporting.generator import _build_prompt_signals


def test_build_prompt_signals_uses_usage_order_and_mechanical_hints():
    diff_report = {
        "new_entries": [
            {"source": "openrouter", "model": "New Top", "rank": 1},
        ],
        "rank_changes": [
            {
                "source": "openrouter",
                "model": "Old Top",
                "old_rank": 1,
                "new_rank": 2,
                "change": -1,
            }
        ],
        "score_changes": [],
    }
    current_state = {
        "openrouter": [
            {
                "model": "Low Usage",
                "rank": 1,
                "score": 0.04,
                "details": {"usage_value": 100, "usage_share_pct": 0.04},
            },
            {
                "model": "High Usage",
                "rank": 2,
                "score": 0.9,
                "details": {"usage_value": 1000, "usage_share_pct": 0.9},
            },
        ]
    }

    signals = _build_prompt_signals(diff_report, current_state)
    assert "mechanical_drop_candidates: openrouter:Old Top" in signals
    assert "openrouter_top_by_usage: High Usage" in signals
