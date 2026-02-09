import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def scrape_llmstats():
    """
    Scrapes LLMStats Leaderboard (via zeroeval API).
    Returns:
    [{'model': str, 'rank': int, 'score': float, 'source': 'llmstats', 'details': dict}]
    """
    url = "https://api.zeroeval.com/leaderboard/models/full?justCanonicals=true"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://llm-stats.com/",
        "Origin": "https://llm-stats.com"
    }

    logging.info(f"Fetching {url}...")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logging.error(f"LLMStats: Network error: {e}")
        return []

    logging.info(f"LLMStats: Extracted {len(data)} raw models.")

    normalized = []
    # Data is usually a list of dicts. We need to find rank and score.
    # LLMStats (ZeroEval) usually has 'elo' or 'score'.
    # We will sort by 'elo' descending to determine rank if explicit rank isn't there.

    # Inspect first item to see structure if possible, but we have to code blindly or safely.
    # Common keys in ZeroEval: 'name', 'elo', 'organization'

    # Sort data by elo just in case
    def get_score(item):
        # Try 'elo', then 'score', then 'rating' - case insensitive
        keys = ['elo', 'score', 'rating', 'overall', 'Elo', 'Score', 'Rating', 'Overall', 'ELO']
        for key in keys:
            if key in item and item[key] is not None:
                try:
                    return float(item[key])
                except:
                    pass
        return 0.0

    # Sort by score descending, then by name ascending for stability
    data.sort(key=lambda x: (get_score(x), x.get('name', '')), reverse=True)
    # Actually reverse=True sorts name descending too (Z-A). That's fine for stability,
    # but strictly (score DESC, name ASC) is better.
    # Python sort is stable. Let's do two sorts or use a tuple with negation.
    # data.sort(key=lambda x: (-get_score(x), x.get('name', ''))) # ASC sort

    data.sort(key=lambda x: x.get('name', '')) # Sort by name ASC first
    data.sort(key=get_score, reverse=True)     # Then by score DESC (stable sort keeps name order for ties)

    for i, item in enumerate(data, 1):
        model_name = item.get('name') or item.get('model') or "Unknown"
        score = get_score(item)

        normalized.append({
            "model": model_name,
            "rank": i,
            "score": score,
            "source": "llmstats",
            "details": item
        })

    return normalized

if __name__ == "__main__":
    import json
    data = scrape_llmstats()
    print(json.dumps(data[:3], indent=2))
