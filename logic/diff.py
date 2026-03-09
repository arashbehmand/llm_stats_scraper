import logging

from logic.history_store import (
    BASELINES_FILE,
    _primary_metric_key_for_source,
    _safe_load_json,
    canonical_model_key,
)

_SCORE_THRESHOLDS = {
    "arena_text": 20.0,
    "arena_vision": 20.0,
    "arena_code": 20.0,
    "llmstats": 20.0,
    "vellum": 2.0,
    "artificial_analysis": 2.0,
    "openrouter": 0.5,
}

_RANK_NEWS_CUTOFF = 10


def _check_new_entry(source, item, baselines):
    """Build a new-entry record. Classifies as 're_entry' if model has a prior baseline."""
    rank = item["rank"]
    canonical_key = canonical_model_key(source, item["model"])
    existing_baseline = baselines.get(canonical_key)

    rank_label = f"#{rank}" if rank is not None else "unranked"
    if existing_baseline:
        first_seen = str(existing_baseline.get("first_seen_at", ""))[:10]
        return {
            "source": source,
            "model": item["model"],
            "rank": rank,
            "score": item["score"],
            "details": item.get("details", {}),
            "context": f"Returned to {rank_label} (previously seen {first_seen})",
            "entry_type": "re_entry",
        }
    return {
        "source": source,
        "model": item["model"],
        "rank": rank,
        "score": item["score"],
        "details": item.get("details", {}),
        "context": f"Debuted {rank_label}",
        "entry_type": "new_model",
    }


def _check_rank_change(source, item, prev_item):
    """Return a rank-change record if the move is significant, else None."""
    rank = item["rank"]
    prev_rank = prev_item["rank"]
    if rank is None or prev_rank is None or rank == prev_rank:
        return None

    diff = prev_rank - rank
    if abs(diff) < 2 and rank > 5 and prev_rank > 5:
        return None

    direction = "CLIMBED" if diff > 0 else "DROPPED"
    return {
        "source": source,
        "model": item["model"],
        "old_rank": prev_rank,
        "new_rank": rank,
        "score": item.get("score"),
        "details": item.get("details", {}),
        "change": diff,
        "context": f"{direction} {abs(diff)} spots (was #{prev_rank}, now #{rank})",
    }


def _check_score_change(source, item, prev_item):
    """Return a score-change record if the delta exceeds the source threshold, else None."""
    try:
        curr_score = float(item.get("score", 0))
        prev_score = float(prev_item.get("score", 0))
    except (ValueError, TypeError):
        return None

    score_diff = curr_score - prev_score
    if abs(score_diff) < _SCORE_THRESHOLDS.get(source, 20.0):
        return None

    return {
        "source": source,
        "model": item["model"],
        "old_score": prev_score,
        "new_score": curr_score,
        "diff": score_diff,
    }


def _is_rank_change_suppressed(rc, new_entry_ranks):
    """Return True if the rank change should be silenced."""
    old_rank, new_rank = rc["old_rank"], rc["new_rank"]

    # Both ranks outside the top-N news window.
    if old_rank > _RANK_NEWS_CUTOFF and new_rank > _RANK_NEWS_CUTOFF:
        return True

    # Minor drop in the lower half of the top-20.
    if rc["change"] < 0 and abs(rc["change"]) <= 2 and old_rank > 8 and new_rank > 8:
        return True

    # Drop fully explained by new entries inserted above this model (cascade).
    if rc["change"] < 0 and new_entry_ranks:
        inserted_above = sum(1 for r in new_entry_ranks if r <= old_rank)
        if (new_rank - (old_rank + inserted_above)) <= 1:
            return True

    return False


def _resolve_new_entry(source, item, prev_family_map, baselines):
    """Build and potentially classify a new-entry record (variant vs new_model)."""
    entry = _check_new_entry(source, item, baselines)
    family = canonical_model_key(source, item["model"])
    siblings = [m for m in prev_family_map.get(family, []) if m and m != item["model"]]
    if siblings:
        entry["entry_type"] = "variant"
        entry["variant_of"] = siblings[0]
        rank = item["rank"]
        entry["context"] = f"Variant appeared at #{rank} (related to {siblings[0]})"
    return entry


def _process_item(
    source, item, prev_map, prev_family_map, baselines, result, new_entry_ranks
):
    """Process one item from current_list and mutate result in-place. Returns early if skipped."""
    model = item["model"]
    if not model or str(model).lower() in ("none", "unknown", "null"):
        return
    rank = item["rank"]
    if rank is not None and rank > 20:
        return

    if model not in prev_map:
        entry = _resolve_new_entry(source, item, prev_family_map, baselines)
        result["new_entries"].append(entry)
        if rank is not None:
            new_entry_ranks.append(rank)
        result["summary"].append(f"[{source}] NEW: {model} at #{rank}")
        return

    if rank is None:
        return

    prev_item = prev_map[model]
    rc = _check_rank_change(source, item, prev_item)
    if rc and not _is_rank_change_suppressed(rc, new_entry_ranks):
        result["rank_changes"].append(rc)
        result["summary"].append(
            f"[{source}] {model} {rc['context'].split()[0]} to #{rc['new_rank']} (was #{rc['old_rank']})"
        )

    sc = _check_score_change(source, item, prev_item)
    if sc:
        result["score_changes"].append(sc)


def _analyze_source(source, current_list, prev_list, baselines):
    """Analyze a single source for new entries, rank changes, and score changes."""
    empty = {"new_entries": [], "rank_changes": [], "score_changes": [], "summary": []}

    curr_metric = _primary_metric_key_for_source(current_list)
    prev_metric = _primary_metric_key_for_source(prev_list)
    if curr_metric and prev_metric and curr_metric != prev_metric:
        logging.info(
            f"Diff: {source} ranking metric changed ({prev_metric} → {curr_metric}), "
            "skipping diff for this source."
        )
        return empty

    prev_map = {item["model"]: item for item in prev_list}
    prev_family_map: dict = {}
    for prev_item in prev_list:
        family = canonical_model_key(source, prev_item.get("model"))
        if family:
            prev_family_map.setdefault(family, []).append(prev_item.get("model"))

    result = {"new_entries": [], "rank_changes": [], "score_changes": [], "summary": []}
    new_entry_ranks: list = []

    for item in current_list:
        _process_item(
            source, item, prev_map, prev_family_map, baselines, result, new_entry_ranks
        )

    return result


def run_diff(current, previous):
    """Compute diff across all sources between current and previous state."""
    if not previous:
        logging.info("Diff: No previous state. First run.")
        return None

    baselines = _safe_load_json(BASELINES_FILE, {})
    report = {"summary": [], "new_entries": [], "rank_changes": [], "score_changes": []}

    for source_name, current_list in current.items():
        prev_list = previous.get(source_name, [])
        partial = _analyze_source(source_name, current_list, prev_list, baselines)
        for key in report:
            report[key].extend(partial[key])

    return report
