import json
import os
from datetime import datetime, timedelta, timezone

BASELINES_FILE = "state/model_baselines.json"
META_FILE = "state/history_meta.json"
EVENTS_DIR = "state/events"
SNAPSHOTS_DIR = "state/snapshots"
LOOKBACK_DAYS = 60

_MONTH_FORMAT = "%Y-%m"

_VARIANT_TOKENS = {
    "thinking",
    "reasoning",
    "high",
    "xhigh",
    "max",
    "effort",
    "preview",
    "latest",
    "adaptive",
    "beta",
}


def _utc_now():
    return datetime.now(timezone.utc)


def _to_iso(ts):
    return ts.isoformat()


def _parse_iso(ts):
    try:
        normalized = ts
        if isinstance(ts, str) and ts.endswith("Z"):
            normalized = ts[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _month_key(ts):
    return ts.strftime(_MONTH_FORMAT)


def _month_start(ts):
    return datetime(ts.year, ts.month, 1, tzinfo=timezone.utc)


def _next_month_start(ts):
    if ts.month == 12:
        return datetime(ts.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(ts.year, ts.month + 1, 1, tzinfo=timezone.utc)


def _parse_month_key(key):
    try:
        parsed = datetime.strptime(key, _MONTH_FORMAT)
    except ValueError:
        return None
    return datetime(parsed.year, parsed.month, 1, tzinfo=timezone.utc)


def _iter_month_keys(start_ts, end_ts):
    cursor = _month_start(start_ts)
    limit = _month_start(end_ts)
    while cursor <= limit:
        yield _month_key(cursor)
        cursor = _next_month_start(cursor)


def _event_file_for_month(month):
    return os.path.join(EVENTS_DIR, f"{month}.jsonl")


def _snapshot_file_for_month(month):
    return os.path.join(SNAPSHOTS_DIR, f"{month}.json")


def _normalize_model_key(name):
    if not name:
        return ""
    lowered = str(name).lower()
    cleaned = []
    for ch in lowered:
        if ch.isalnum() or ch in {" ", "-", "_"}:
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    tokens = "".join(cleaned).replace("_", " ").replace("-", " ").split()
    filtered = []
    for token in tokens:
        if token.isdigit() and len(token) >= 6:
            continue
        if token in _VARIANT_TOKENS:
            continue
        filtered.append(token)
    return " ".join(filtered)


def canonical_model_key(source, model):
    return f"{source}:{_normalize_model_key(model)}"


def _safe_load_json(path, fallback):
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return fallback


def _safe_dump_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _append_jsonl(path, rows):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def _write_month_snapshot(month, state, snapshot_ts):
    payload = {"month": month, "snapshot_at": snapshot_ts, "state": state}
    _safe_dump_json(_snapshot_file_for_month(month), payload)


def _prune_old_partitions(cutoff_ts):
    for root, ext in ((EVENTS_DIR, ".jsonl"), (SNAPSHOTS_DIR, ".json")):
        if not os.path.isdir(root):
            continue
        for filename in os.listdir(root):
            if not filename.endswith(ext):
                continue
            month_key = filename[: -len(ext)]
            month_ts = _parse_month_key(month_key)
            if not month_ts:
                continue
            month_end = _next_month_start(month_ts)
            if month_end < cutoff_ts:
                try:
                    os.remove(os.path.join(root, filename))
                except OSError:
                    continue


def _build_model_map(state):
    model_map = {}
    for source, models in (state or {}).items():
        for item in models or []:
            model = item.get("model")
            if not model:
                continue
            model_map[(source, model)] = item
    return model_map


def _compute_item_delta(current_item, previous_item):
    if not previous_item:
        return {
            "created": True,
            "rank": current_item.get("rank"),
            "score": current_item.get("score"),
            "details": current_item.get("details", {}),
        }

    delta = {}
    for field in ("rank", "score"):
        prev_val = previous_item.get(field)
        cur_val = current_item.get(field)
        if prev_val != cur_val:
            delta[field] = {"from": prev_val, "to": cur_val}

    prev_details = previous_item.get("details", {}) or {}
    cur_details = current_item.get("details", {}) or {}
    details_delta = {}
    for key in set(prev_details.keys()) | set(cur_details.keys()):
        if prev_details.get(key) != cur_details.get(key):
            details_delta[key] = {
                "from": prev_details.get(key),
                "to": cur_details.get(key),
            }
    if details_delta:
        delta["details"] = details_delta

    return delta


def update_history(current_state, previous_state):
    now = _utc_now()
    now_iso = _to_iso(now)
    month = _month_key(now)
    cutoff = now - timedelta(days=LOOKBACK_DAYS)

    baselines = _safe_load_json(BASELINES_FILE, {})
    meta = _safe_load_json(META_FILE, {})
    prev_map = _build_model_map(previous_state)
    events = []

    previous_month = meta.get("last_seen_month")
    if previous_month and previous_month != month and previous_state:
        _write_month_snapshot(previous_month, previous_state, now_iso)

    for source, models in (current_state or {}).items():
        for item in models or []:
            model = item.get("model")
            if not model:
                continue
            identity = canonical_model_key(source, model)
            baseline = baselines.get(identity)
            if not baseline:
                baselines[identity] = {
                    "source": source,
                    "canonical_key": identity,
                    "first_seen_at": now_iso,
                    "base_model_name": model,
                    "base_state": item,
                }
                events.append(
                    {
                        "ts": now_iso,
                        "source": source,
                        "canonical_key": identity,
                        "model": model,
                        "event_type": "baseline_created",
                        "delta": {"created": True},
                    }
                )
                continue

            prev_item = prev_map.get((source, model))
            delta = _compute_item_delta(item, prev_item)
            if delta:
                events.append(
                    {
                        "ts": now_iso,
                        "source": source,
                        "canonical_key": identity,
                        "model": model,
                        "event_type": "state_diff",
                        "delta": delta,
                    }
                )

    _safe_dump_json(BASELINES_FILE, baselines)
    _append_jsonl(_event_file_for_month(month), events)
    _write_month_snapshot(month, current_state, now_iso)
    _safe_dump_json(
        META_FILE,
        {
            "last_seen_at": now_iso,
            "last_seen_month": month,
            "lookback_days": LOOKBACK_DAYS,
        },
    )
    _prune_old_partitions(cutoff)


def _extract_change(value):
    if isinstance(value, dict):
        return value.get("from"), value.get("to")
    if value is None:
        return None, None
    return None, value


def _format_value(value):
    if value is None:
        return "?"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _format_change(field, before, after):
    if before is None and after is None:
        return ""
    if before == after:
        return ""
    if before is None:
        return f"{field}={_format_value(after)}"
    return f"{field}:{_format_value(before)}->{_format_value(after)}"


def _summarize_model_history(events, baseline):
    events_sorted = sorted(
        events,
        key=lambda evt: _parse_iso(evt.get("ts"))
        or datetime.min.replace(tzinfo=timezone.utc),
    )

    base_state = (
        (baseline or {}).get("base_state", {}) if isinstance(baseline, dict) else {}
    )
    first_seen = (
        (baseline or {}).get("first_seen_at") if isinstance(baseline, dict) else None
    )
    if not first_seen and events_sorted:
        first_seen = events_sorted[0].get("ts")

    base_rank = base_state.get("rank")
    base_score = base_state.get("score")
    latest_rank = base_rank
    latest_score = base_score
    rank_moves = 0
    score_moves = 0
    last_change = ""

    for evt in events_sorted:
        delta = evt.get("delta", {})
        if not isinstance(delta, dict):
            continue

        rank_from, rank_to = _extract_change(delta.get("rank"))
        score_from, score_to = _extract_change(delta.get("score"))
        rank_changed = rank_from != rank_to and (
            rank_from is not None or rank_to is not None
        )
        score_changed = score_from != score_to and (
            score_from is not None or score_to is not None
        )

        if rank_changed:
            rank_moves += 1
        if score_changed:
            score_moves += 1

        if rank_to is not None:
            latest_rank = rank_to
        elif rank_from is not None and latest_rank is None:
            latest_rank = rank_from

        if score_to is not None:
            latest_score = score_to
        elif score_from is not None and latest_score is None:
            latest_score = score_from

        if rank_changed or score_changed:
            parts = []
            rank_part = _format_change("rank", rank_from, rank_to)
            score_part = _format_change("score", score_from, score_to)
            if rank_part:
                parts.append(rank_part)
            if score_part:
                parts.append(score_part)
            ts = evt.get("ts", "")
            last_change = f"{ts} ({'; '.join(parts)})"

    rank_part = _format_change("rank", base_rank, latest_rank)
    score_part = _format_change("score", base_score, latest_score)
    seen_part = f"first_seen={str(first_seen)[:10]}" if first_seen else "first_seen=?"
    moves_part = f"moves(rank={rank_moves},score={score_moves})"

    summary_parts = [seen_part]
    if rank_part:
        summary_parts.append(rank_part)
    if score_part:
        summary_parts.append(score_part)
    summary_parts.append(moves_part)
    if last_change:
        summary_parts.append(f"last_change={last_change}")

    return " | ".join(summary_parts)


def build_history_context(
    diff_report, max_events_per_model=3, lookback_days=LOOKBACK_DAYS, max_models=12
):
    if not diff_report:
        return ""
    ordered_keys = []
    key_to_label = {}
    for bucket in ("new_entries", "rank_changes", "score_changes"):
        for row in diff_report.get(bucket, []):
            source = row.get("source")
            model = row.get("model")
            if source and model:
                key = canonical_model_key(source, model)
                if key not in key_to_label:
                    key_to_label[key] = (source, model)
                    ordered_keys.append(key)
                    if len(ordered_keys) >= max_models:
                        break
        if len(ordered_keys) >= max_models:
            break
    if not ordered_keys:
        return ""

    now = _utc_now()
    cutoff = now - timedelta(days=lookback_days)
    month_keys = list(_iter_month_keys(cutoff, now))
    recent = {k: [] for k in ordered_keys}

    for month in month_keys:
        path = _event_file_for_month(month)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    evt = json.loads(line)
                    evt_ts = _parse_iso(evt.get("ts"))
                    if not evt_ts or evt_ts < cutoff:
                        continue
                    key = evt.get("canonical_key")
                    if key in recent:
                        recent[key].append(evt)
        except (OSError, json.JSONDecodeError):
            continue

    baselines = _safe_load_json(BASELINES_FILE, {})
    lines = []
    for key in ordered_keys:
        events = recent.get(key, [])
        source, model = key_to_label[key]
        if not events and key not in baselines:
            continue
        cropped = events[-max_events_per_model:] if max_events_per_model > 0 else events
        summary = _summarize_model_history(cropped, baselines.get(key))
        lines.append(f"- {source}:{model} | {summary}")
    return "\n".join(lines)
