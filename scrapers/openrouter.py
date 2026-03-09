import json
import logging
from datetime import datetime, timedelta, timezone

import requests

# Models listed on OpenRouter within this window are flagged as new listings
NEW_LISTING_LOOKBACK_HOURS = 48


def _find_in_rsc(json_payload, predicate, depth=0):
    """Recursively search RSC payload for the first object matching predicate."""
    if depth > 15:
        return None
    if isinstance(json_payload, dict):
        result = predicate(json_payload)
        if result is not None:
            return result
        for v in json_payload.values():
            res = _find_in_rsc(v, predicate, depth + 1)
            if res is not None:
                return res
    elif isinstance(json_payload, list):
        for item in json_payload:
            res = _find_in_rsc(item, predicate, depth + 1)
            if res is not None:
                return res
    return None


def _is_per_model_token_timeseries(obj):
    """
    Match a dict containing a per-model weekly token time-series:
      {"data": [{"x": "2026-03-02", "ys": {"model/slug": tokens, "Others": N}}, ...]}
    Rejects per-author charts (where ys keys have no "/").
    """
    data = obj.get("data")
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not (isinstance(first, dict) and "x" in first and "ys" in first):
        return None
    # Per-model keys contain "/" (e.g. "google/gemini-2.5-flash"); author keys don't.
    ys_keys = list(first.get("ys", {}).keys())
    if not any("/" in k for k in ys_keys):
        return None
    return data


def _is_model_list(obj):
    """Match the per-model rankings list: {"data": [{id, slug, name, request_count, ...}]}."""
    data = obj.get("data")
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if isinstance(first, dict) and "request_count" in first:
        return data
    return None


def _parse_rsc_line(line):
    """Parse an RSC payload line (<chunk_id>:<json>) and return the JSON object."""
    parts = line.split(":", 1)
    if len(parts) != 2:
        return None
    try:
        return json.loads(parts[1])
    except (json.JSONDecodeError, ValueError):
        return None


def _fetch_new_openrouter_models():
    """
    Fetches models recently listed on OpenRouter via the frontend API.
    Returns a list of model dicts with created_at within NEW_LISTING_LOOKBACK_HOURS.
    """
    try:
        response = requests.get(
            "https://openrouter.ai/api/frontend/models",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        models = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(models, list):
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=NEW_LISTING_LOOKBACK_HOURS
        )
        new_models = []
        for m in models:
            if m.get("hidden"):
                continue
            created_str = m.get("created_at") or m.get("createdAt")
            if not created_str:
                continue
            try:
                created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if created_at >= cutoff:
                    new_models.append(m)
            except (ValueError, AttributeError):
                continue

        logging.info(
            f"OpenRouter new listings: {len(new_models)} models created in last "
            f"{NEW_LISTING_LOOKBACK_HOURS}h."
        )
        return new_models
    except Exception as e:
        logging.warning(f"OpenRouter: Failed to fetch new model listings: {e}")
        return []


def scrape_openrouter():
    """
    Scrapes the OpenRouter rankings page for LLM leaderboard data.

    Uses weekly TOKEN COUNTS (matching the OpenRouter UI leaderboard) as the
    primary ranking metric, derived from the stacked time-series chart in the RSC
    payload. Only the top ~9 models have token data; the rest are excluded from
    ranked results (rank=None).

    Additionally detects newly listed models via the frontend API and appends
    them as unranked entries so the diff engine can flag them as new arrivals.

    Score field: last complete week's usage share (stable, for diff comparison).
    details.current_week_share_pct: share in the current partial week (early signal /
    projected full-week share, since projection factor cancels in ratio math).
    """
    url = "https://openrouter.ai/rankings?view=week"
    headers = {
        "RSC": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        content = response.text

        token_timeseries = None
        model_list = None

        for line in content.split("\n"):
            if not line.strip():
                continue
            payload = _parse_rsc_line(line)
            if payload is None:
                continue

            if token_timeseries is None and '"ys"' in line:
                token_timeseries = _find_in_rsc(payload, _is_per_model_token_timeseries)

            if model_list is None and '"request_count"' in line:
                model_list = _find_in_rsc(payload, _is_model_list)

            if token_timeseries is not None and model_list is not None:
                break

        # Fetch new model listings regardless of RSC data availability.
        new_models = _fetch_new_openrouter_models()

        if not token_timeseries and not model_list:
            logging.warning(
                "OpenRouter: No RSC data found; returning new listings only."
            )
            # Still return new listing entries so the diff engine can detect them.
            return [
                {
                    "model": m.get("name") or m.get("permaslug") or m.get("slug"),
                    "rank": None,
                    "score": 0.0,
                    "source": "openrouter",
                    "details": {
                        "slug": m.get("permaslug") or m.get("slug"),
                        "base_slug": m.get("slug"),
                        "is_new_listing": True,
                        "created_at": m.get("created_at"),
                        "updated_at": m.get("updated_at"),
                        "author": m.get("author"),
                        "context_length": m.get("context_length"),
                        "description": (m.get("description") or "")[:200],
                        "input_modalities": m.get("input_modalities"),
                        "supports_reasoning": m.get("supports_reasoning"),
                        "usage_metric_key": "new_listing",
                        "usage_value": 0.0,
                        "usage_share_pct": None,
                        "usage_total": 1.0,
                        "current_week_tokens": None,
                        "current_week_share_pct": None,
                    },
                }
                for m in new_models
                if not m.get("hidden")
            ]

        # --- Identify last complete week and current partial week ---
        # Entries are chronological; last = current partial week, second-to-last = last complete week.
        last_week_entry = None
        current_week_entry = None
        if token_timeseries:
            entries_sorted = sorted(token_timeseries, key=lambda e: e.get("x", ""))
            if len(entries_sorted) >= 2:
                last_week_entry = entries_sorted[-2]
                current_week_entry = entries_sorted[-1]
            elif len(entries_sorted) == 1:
                last_week_entry = entries_sorted[0]
            logging.info(
                f"OpenRouter: last_week={last_week_entry and last_week_entry['x']}, "
                f"current_partial={current_week_entry and current_week_entry['x']}"
            )

        last_week_ys = (last_week_entry or {}).get("ys", {})
        current_week_ys = (
            (current_week_entry or {}).get("ys", {}) if current_week_entry else {}
        )

        last_week_total = sum(last_week_ys.values()) or 1.0
        current_week_total = sum(current_week_ys.values()) or 1.0

        # --- Model name lookup from request_count list ---
        model_info_by_slug = {}
        if model_list:
            for entry in model_list:
                slug = entry.get("slug") or entry.get("id")
                if slug:
                    model_info_by_slug[slug] = entry

        # --- Build ranked entries from token data (tier 1) ---
        normalized = []
        ranked_slugs = set()

        for slug, last_week_tokens in sorted(
            ((s, t) for s, t in last_week_ys.items() if s != "Others"),
            key=lambda x: -x[1],
        ):
            ranked_slugs.add(slug)
            info = model_info_by_slug.get(slug, {})
            name = info.get("name") or slug

            last_week_share_pct = round((last_week_tokens / last_week_total) * 100.0, 3)

            current_week_tokens = current_week_ys.get(slug, 0)
            current_week_share_pct = (
                round((current_week_tokens / current_week_total) * 100.0, 3)
                if current_week_total > 0
                else None
            )

            normalized.append(
                {
                    "model": name,
                    "rank": 0,  # assigned after sort
                    "score": last_week_share_pct,
                    "source": "openrouter",
                    "details": {
                        **info,
                        "slug": slug,
                        "usage_metric_key": "token_count",
                        "usage_value": float(last_week_tokens),
                        "usage_share_pct": last_week_share_pct,
                        "usage_total": last_week_total,
                        "current_week_tokens": float(current_week_tokens),
                        "current_week_share_pct": current_week_share_pct,
                    },
                }
            )

        # Sort tier-1 by last week tokens desc and assign ranks
        normalized.sort(key=lambda r: -r["details"]["usage_value"])
        for rank, row in enumerate(normalized, start=1):
            row["rank"] = rank

        # --- Unranked entries from request_count list (rank=None, excluded from chart) ---
        for slug, info in model_info_by_slug.items():
            if slug in ranked_slugs:
                continue
            normalized.append(
                {
                    "model": info.get("name") or slug,
                    "rank": None,
                    "score": 0.0,
                    "source": "openrouter",
                    "details": {
                        **info,
                        "slug": slug,
                        "usage_metric_key": "request_count",
                        "usage_value": float(info.get("request_count", 0)),
                        "usage_share_pct": None,
                        "usage_total": last_week_total,
                        "current_week_tokens": None,
                        "current_week_share_pct": None,
                    },
                }
            )

        logging.info(
            f"OpenRouter: {len([r for r in normalized if r['rank'] is not None])} ranked "
            f"(token-based), {len([r for r in normalized if r['rank'] is None])} unranked."
        )

        # --- New model listings from frontend API (already fetched above) ---
        all_known_slugs = set(model_info_by_slug.keys()) | ranked_slugs
        # Also check permaslugs of known models to avoid duplicates
        known_permaslugs = {
            info.get("slug") for info in model_info_by_slug.values() if info.get("slug")
        }

        for new_model in new_models:
            permaslug = new_model.get("permaslug") or new_model.get("slug")
            base_slug = new_model.get("slug")
            if not permaslug:
                continue
            # Skip if already in ranked or request_count list
            if permaslug in all_known_slugs or base_slug in all_known_slugs:
                continue
            if permaslug in known_permaslugs or base_slug in known_permaslugs:
                continue

            normalized.append(
                {
                    "model": new_model.get("name") or permaslug,
                    "rank": None,
                    "score": 0.0,
                    "source": "openrouter",
                    "details": {
                        "slug": permaslug,
                        "base_slug": base_slug,
                        "is_new_listing": True,
                        "created_at": new_model.get("created_at"),
                        "updated_at": new_model.get("updated_at"),
                        "author": new_model.get("author"),
                        "context_length": new_model.get("context_length"),
                        "description": (new_model.get("description") or "")[:200],
                        "input_modalities": new_model.get("input_modalities"),
                        "supports_reasoning": new_model.get("supports_reasoning"),
                        "usage_metric_key": "new_listing",
                        "usage_value": 0.0,
                        "usage_share_pct": None,
                        "usage_total": last_week_total,
                        "current_week_tokens": None,
                        "current_week_share_pct": None,
                    },
                }
            )

        new_listing_count = len(
            [r for r in normalized if r.get("details", {}).get("is_new_listing")]
        )
        if new_listing_count:
            logging.info(f"OpenRouter: {new_listing_count} new model listings added.")

        return normalized

    except Exception as e:
        logging.error(f'Error scraping OpenRouter: {e}"')
        return []
