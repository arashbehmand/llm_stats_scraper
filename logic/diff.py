import logging

_SCORE_THRESHOLDS = {
    "arena_text": 20.0,
    "arena_vision": 20.0,
    "arena_code": 20.0,
    "llmstats": 20.0,
    "vellum": 2.0,
    "artificial_analysis": 2.0,
    "openrouter": 0.5,
}


def _find_displaced_model(rank, prev_list):
    """Find which model was at this rank in the previous list."""
    for item in prev_list:
        if item["rank"] == rank:
            return item["model"]
    return None


def _check_new_entry(source, item, prev_list):
    """Build a new-entry record if the model just appeared in the top 20."""
    rank = item["rank"]
    displaced = _find_displaced_model(rank, prev_list)
    context = f"Debuted at #{rank}"
    if displaced:
        context += f", likely pushing {displaced} down."

    return {
        "source": source,
        "model": item["model"],
        "rank": rank,
        "score": item["score"],
        "details": item.get("details", {}),
        "context": context,
    }


def _check_rank_change(source, item, prev_item):
    """Return a rank-change record if the move is significant, else None."""
    rank = item["rank"]
    prev_rank = prev_item["rank"]
    if rank == prev_rank:
        return None

    diff = prev_rank - rank  # positive means the model climbed
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
    threshold = _SCORE_THRESHOLDS.get(source, 20.0)
    if abs(score_diff) < threshold:
        return None

    return {
        "source": source,
        "model": item["model"],
        "old_score": prev_score,
        "new_score": curr_score,
        "diff": score_diff,
    }


def _analyze_source(source, current_list, prev_list):
    """Analyze a single source for new entries, rank changes, and score changes."""
    prev_map = {item["model"]: item for item in prev_list}
    result = {"new_entries": [], "rank_changes": [], "score_changes": [], "summary": []}

    for item in current_list:
        model = item["model"]
        if not model or str(model).lower() in ("none", "unknown", "null"):
            continue
        if item["rank"] > 20:
            continue

        if model not in prev_map:
            entry = _check_new_entry(source, item, prev_list)
            result["new_entries"].append(entry)
            result["summary"].append(f"[{source}] NEW: {model} at #{item['rank']}")
            continue

        prev_item = prev_map[model]

        rc = _check_rank_change(source, item, prev_item)
        if rc:
            result["rank_changes"].append(rc)
            result["summary"].append(
                f"[{source}] {model} {rc['context'].split()[0]} to #{rc['new_rank']} (was #{rc['old_rank']})"
            )

        sc = _check_score_change(source, item, prev_item)
        if sc:
            result["score_changes"].append(sc)

    return result


def run_diff(current, previous):
    """Compute diff across all sources between current and previous state."""
    if not previous:
        logging.info("Diff: No previous state. First run.")
        return None

    report = {"summary": [], "new_entries": [], "rank_changes": [], "score_changes": []}

    for source_name, current_list in current.items():
        prev_list = previous.get(source_name, [])
        partial = _analyze_source(source_name, current_list, prev_list)
        for key in report:
            report[key].extend(partial[key])

    return report
