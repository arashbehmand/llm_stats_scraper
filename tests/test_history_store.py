import json
from datetime import datetime, timezone
from pathlib import Path

import logic.history_store as hs


def _row(model, rank, score=100.0, details=None):
    return {
        "model": model,
        "rank": rank,
        "score": score,
        "details": details or {},
    }


def _configure_state_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(
        hs, "BASELINES_FILE", str(tmp_path / "state" / "model_baselines.json")
    )
    monkeypatch.setattr(hs, "META_FILE", str(tmp_path / "state" / "history_meta.json"))
    monkeypatch.setattr(hs, "EVENTS_DIR", str(tmp_path / "state" / "events"))
    monkeypatch.setattr(hs, "SNAPSHOTS_DIR", str(tmp_path / "state" / "snapshots"))


def test_update_history_writes_monthly_event_and_snapshot(tmp_path, monkeypatch):
    _configure_state_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(
        hs, "_utc_now", lambda: datetime(2026, 2, 10, tzinfo=timezone.utc)
    )

    current = {"openrouter": [_row("gpt-5.2", 1, 1.0, {"usage_share_pct": 0.1})]}
    hs.update_history(current, {})

    events_file = Path(hs.EVENTS_DIR) / "2026-02.jsonl"
    snapshot_file = Path(hs.SNAPSHOTS_DIR) / "2026-02.json"
    baselines_file = Path(hs.BASELINES_FILE)
    meta_file = Path(hs.META_FILE)

    assert events_file.exists()
    assert snapshot_file.exists()
    assert baselines_file.exists()
    assert meta_file.exists()

    events = [
        json.loads(line)
        for line in events_file.read_text(encoding="utf-8").splitlines()
    ]
    assert len(events) == 1
    assert events[0]["event_type"] == "baseline_created"

    snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    assert snapshot["state"] == current


def test_update_history_month_rollover_persists_previous_month_snapshot(
    tmp_path, monkeypatch
):
    _configure_state_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(
        hs, "_utc_now", lambda: datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
    )

    meta_path = Path(hs.META_FILE)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps({"last_seen_month": "2026-01"}), encoding="utf-8")

    previous = {"openrouter": [_row("gpt-5.1", 1, 0.8)]}
    current = {"openrouter": [_row("gpt-5.2", 1, 1.0)]}
    hs.update_history(current, previous)

    jan_snapshot = Path(hs.SNAPSHOTS_DIR) / "2026-01.json"
    feb_snapshot = Path(hs.SNAPSHOTS_DIR) / "2026-02.json"
    assert jan_snapshot.exists()
    assert feb_snapshot.exists()

    jan_payload = json.loads(jan_snapshot.read_text(encoding="utf-8"))
    feb_payload = json.loads(feb_snapshot.read_text(encoding="utf-8"))
    assert jan_payload["state"] == previous
    assert feb_payload["state"] == current


def test_build_history_context_reads_only_recent_lookback(tmp_path, monkeypatch):
    _configure_state_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(
        hs, "_utc_now", lambda: datetime(2026, 4, 1, tzinfo=timezone.utc)
    )

    key = hs.canonical_model_key("openrouter", "gpt-5.2")
    events_dir = Path(hs.EVENTS_DIR)
    events_dir.mkdir(parents=True, exist_ok=True)

    jan_file = events_dir / "2026-01.jsonl"
    mar_file = events_dir / "2026-03.jsonl"

    jan_events = [
        {
            "ts": "2026-01-10T00:00:00+00:00",
            "source": "openrouter",
            "canonical_key": key,
            "model": "gpt-5.2",
            "event_type": "state_diff",
            "delta": {"rank": {"from": 2, "to": 1}},
        }
    ]
    mar_events = [
        {
            "ts": "2026-03-05T00:00:00+00:00",
            "source": "openrouter",
            "canonical_key": key,
            "model": "gpt-5.2",
            "event_type": "state_diff",
            "delta": {"score": {"from": 0.9, "to": 1.0}},
        },
        {
            "ts": "2026-03-18T00:00:00+00:00",
            "source": "openrouter",
            "canonical_key": key,
            "model": "gpt-5.2",
            "event_type": "state_diff",
            "delta": {"rank": {"from": 1, "to": 2}},
        },
        {
            "ts": "2026-03-29T00:00:00+00:00",
            "source": "openrouter",
            "canonical_key": key,
            "model": "gpt-5.2",
            "event_type": "state_diff",
            "delta": {"rank": {"from": 2, "to": 1}},
        },
    ]

    jan_file.write_text(
        "\n".join(json.dumps(evt) for evt in jan_events) + "\n", encoding="utf-8"
    )
    mar_file.write_text(
        "\n".join(json.dumps(evt) for evt in mar_events) + "\n", encoding="utf-8"
    )

    diff_report = {"new_entries": [{"source": "openrouter", "model": "gpt-5.2"}]}
    history = hs.build_history_context(
        diff_report,
        max_events_per_model=2,
        lookback_days=60,
    )

    assert "2026-01-10T00:00:00+00:00" not in history
    assert "2026-03-18T00:00:00+00:00" in history
    assert "2026-03-29T00:00:00+00:00" in history
    assert "2026-03-05T00:00:00+00:00" not in history
