import json
import logging

import requests

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def scrape_arena(category="text"):
    """
    Scrapes the LMSYS Arena Leaderboard.
    Returns a list of standardized dictionaries:
    [{'model': str, 'rank': int, 'score': float, 'source': 'arena', 'details': dict}]
    """
    url = f"https://arena.ai/leaderboard/{category}"
    headers = {
        "RSC": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        logging.info(f"Fetching {url}...")
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        for line in response.text.split("\n"):
            if line.startswith("b:"):
                json_content = line[2:]
                try:
                    data = json.loads(json_content)
                    for item in data:
                        if isinstance(item, dict) and "leaderboard" in item:
                            entries = item["leaderboard"].get("entries", [])

                            logging.info(
                                f"Arena: Extracted {len(entries)} models ({category})."
                            )

                            # Normalize immediately
                            normalized = []
                            for entry in entries:
                                try:
                                    normalized.append(
                                        {
                                            "model": entry.get(
                                                "modelDisplayName", "Unknown"
                                            ),
                                            "rank": int(entry.get("rank", 9999)),
                                            "score": float(entry.get("rating", 0)),
                                            "source": f"arena_{category}",
                                            "details": entry,  # Keep raw data
                                        }
                                    )
                                except (ValueError, TypeError):
                                    continue  # Skip malformed entries

                            return normalized

                except json.JSONDecodeError:
                    continue

        logging.warning(f"Arena: No data found for {category}")
        return []

    except Exception as e:
        logging.error(f"Arena Scraper Error ({category}): {e}")
        return []


if __name__ == "__main__":
    data = scrape_arena("text")
    print(json.dumps(data[:3], indent=2))
