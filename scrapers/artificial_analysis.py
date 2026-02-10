import json
import logging

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

URL = "https://artificialanalysis.ai/leaderboards/models"
HEADERS = {
    "RSC": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def find_leaderboard_data(obj):
    """
    Recursively search for a list of objects that looks like the leaderboard data.
    We identify it by the presence of 'intelligence_index' key in the objects.
    """
    if isinstance(obj, list):
        # Check if list elements look like the leaderboard rows
        if len(obj) > 0 and isinstance(obj[0], dict) and "intelligence_index" in obj[0]:
            return obj
        for item in obj:
            res = find_leaderboard_data(item)
            if res:
                return res
    elif isinstance(obj, dict):
        for key, value in obj.items():
            res = find_leaderboard_data(value)
            if res:
                return res
    return None


def scrape_artificial_analysis():
    """
    Scrapes Artificial Analysis Leaderboard.
    Returns:
    [{'model': str, 'rank': int, 'score': float, 'source': 'artificial_analysis', 'details': dict}]
    """
    logging.info(f"Fetching {URL}...")
    try:
        response = requests.get(URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Artificial Analysis: Network error: {e}")
        return []

    lines = response.text.split("\n")
    all_data = []

    for line in lines:
        if "intelligence_index" in line:
            try:
                parts = line.split(":", 1)
                if len(parts) < 2:
                    continue

                payload = parts[1].strip()
                if payload.startswith("I"):
                    payload = payload[1:]

                if not (payload.startswith("[") or payload.startswith("{")):
                    continue

                try:
                    data = json.loads(payload)
                    found = find_leaderboard_data(data)
                    if found:
                        all_data = found
                        break
                except json.JSONDecodeError:
                    pass
            except Exception:
                pass

    if not all_data:
        logging.warning("Artificial Analysis: No data found.")
        return []

    logging.info(f"Artificial Analysis: Extracted {len(all_data)} raw models.")

    normalized = []
    # Rank models based on intelligence_index descending
    # Ensure intelligence_index is numeric
    valid_entries = []
    for entry in all_data:
        try:
            score = float(entry.get("intelligence_index", 0))
            valid_entries.append((entry, score))
        except (ValueError, TypeError):
            continue

    # Sort by score desc
    valid_entries.sort(key=lambda x: x[1], reverse=True)

    for rank, (entry, score) in enumerate(valid_entries, 1):
        normalized.append(
            {
                "model": entry.get(
                    "name", "Unknown"
                ),  # Assuming 'name' field exists, fallback required if different
                "rank": rank,
                "score": score,
                "source": "artificial_analysis",
                "details": entry,
            }
        )

    return normalized


if __name__ == "__main__":
    data = scrape_artificial_analysis()
    print(json.dumps(data[:3], indent=2))
