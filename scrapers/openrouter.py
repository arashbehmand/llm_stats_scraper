import requests
import json
import logging

def scrape_openrouter():
    """
    Scrapes the OpenRouter rankings page for LLM leaderboard data using RSC API.
    Returns a normalized list of dictionaries matching other scrapers' format.
    """
    url = "https://openrouter.ai/rankings?view=week"
    headers = {
        "RSC": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        content = response.text
        
        # Find the line containing the data
        for line in content.split('\n'):
            if '"data":[{' in line:
                # RSC line format: <id>:<json_value>
                parts = line.split(':', 1)
                if len(parts) == 2:
                    json_payload = json.loads(parts[1])
                    
                    # Navigate the RSC structure recursively
                    # Structure: ["$","$L4e",null,{"children":["$","$L52",null,{"data":[...]}]}]
                    def find_data(obj, depth=0):
                        if depth > 15:
                            return None
                        if isinstance(obj, dict):
                            if 'data' in obj and isinstance(obj['data'], list) and len(obj['data']) > 0:
                                first = obj['data'][0]
                                if isinstance(first, dict) and 'request_count' in first:
                                    return obj['data']
                            for v in obj.values():
                                res = find_data(v, depth+1)
                                if res: return res
                        elif isinstance(obj, list):
                            for item in obj:
                                res = find_data(item, depth+1)
                                if res: return res
                        return None

                    raw_data = find_data(json_payload)
                    if raw_data:
                        # Normalize data to match other scrapers' format
                        normalized = []
                        for rank, entry in enumerate(raw_data, start=1):
                            normalized.append({
                                "model": entry.get("name", "Unknown"),
                                "rank": rank,
                                "score": float(entry.get("request_count", 0)),  # Use request_count as the metric
                                "source": "openrouter",
                                "details": entry  # Keep raw data
                            })
                        
                        logging.info(f"OpenRouter: Extracted {len(normalized)} models.")
                        return normalized
                
        logging.warning("OpenRouter: No data line found in response.")
        return []

    except Exception as e:
        logging.error(f"Error scraping OpenRouter: {e}\"")
        return []
