import json
import logging

import requests


def _extract_usage_value(entry):
    """
    Return the best available usage metric for share normalization.
    Prefer token-based counters when available; fallback to request_count.
    """
    for key in ("token_count", "total_tokens", "tokens", "request_count"):
        value = entry.get(key)
        if value is None:
            continue
        try:
            return float(value), key
        except (TypeError, ValueError):
            continue
    return 0.0, "unknown"


def scrape_openrouter():
    """
    Scrapes the OpenRouter rankings page for LLM leaderboard data using RSC API.
    Returns a normalized list of dictionaries matching other scrapers' format.
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

        # Find the line containing the data
        for line in content.split("\n"):
            if '"data":[{' in line:
                # RSC line format: <id>:<json_value>
                parts = line.split(":", 1)
                if len(parts) == 2:
                    json_payload = json.loads(parts[1])

                    # Navigate the RSC structure recursively
                    # Structure: ["$","$L4e",null,{"children":["$","$L52",null,{"data":[...]}]}]
                    def find_data(obj, depth=0):
                        if depth > 15:
                            return None
                        if isinstance(obj, dict):
                            if (
                                "data" in obj
                                and isinstance(obj["data"], list)
                                and len(obj["data"]) > 0
                            ):
                                first = obj["data"][0]
                                if isinstance(first, dict) and "request_count" in first:
                                    return obj["data"]
                            for v in obj.values():
                                res = find_data(v, depth + 1)
                                if res:
                                    return res
                        elif isinstance(obj, list):
                            for item in obj:
                                res = find_data(item, depth + 1)
                                if res:
                                    return res
                        return None

                    raw_data = find_data(json_payload)
                    if raw_data:
                        # Build a comparable usage-share score to avoid false positives
                        # from platform-wide traffic growth.
                        usage_values = []
                        metric_key = "unknown"
                        for entry in raw_data:
                            usage_value, this_key = _extract_usage_value(entry)
                            usage_values.append(usage_value)
                            if metric_key == "unknown" and this_key != "unknown":
                                metric_key = this_key

                        total_usage = sum(usage_values)
                        if total_usage <= 0:
                            total_usage = 1.0

                        # Normalize to shared schema, then assign rank after sorting by usage.
                        normalized = []
                        for idx, entry in enumerate(raw_data):
                            usage_value = usage_values[idx]
                            usage_share_pct = round(
                                (usage_value / total_usage) * 100.0, 3
                            )
                            normalized.append(
                                {
                                    "model": entry.get("name", "Unknown"),
                                    "rank": 0,  # assigned after sorting
                                    "score": usage_share_pct,  # Usage share percentage (0-100)
                                    "source": "openrouter",
                                    "details": {
                                        **entry,
                                        "usage_metric_key": metric_key,
                                        "usage_value": usage_value,
                                        "usage_share_pct": usage_share_pct,
                                        "usage_total": total_usage,
                                    },
                                }
                            )

                        normalized.sort(
                            key=lambda row: (
                                -float(row.get("details", {}).get("usage_value", 0.0)),
                                row.get("model", ""),
                            )
                        )
                        for rank, row in enumerate(normalized, start=1):
                            row["rank"] = rank

                        logging.info(
                            f"OpenRouter: Extracted {len(normalized)} models "
                            f"(normalized by {metric_key} share)."
                        )
                        return normalized

        logging.warning("OpenRouter: No data line found in response.")
        return []

    except Exception as e:
        logging.error(f'Error scraping OpenRouter: {e}"')
        return []
