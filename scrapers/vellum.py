import json
import logging
import re

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def scrape_vellum():
    """
    Scrapes the Vellum LLM Leaderboard.
    Assumption based on logs:
    dataModels keys are MODEL NAMES.
    Inside each value, there are xValues (metrics) and yValues (scores) (or swapped).
    We need to extract one specific metric (e.g. 'Elo' or 'Win Rate') for each model.
    """
    url = "https://www.vellum.ai/llm-leaderboard"
    logging.info(f"Fetching {url}...")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        html_content = response.text
    except Exception as e:
        logging.error(f"Vellum: Network error: {e}")
        return []

    pattern = re.compile(r"var dataModels\s*=\s*({.*?});", re.DOTALL)
    match = pattern.search(html_content)

    if not match:
        logging.error("Vellum: Could not find 'dataModels' variable in HTML.")
        return []

    json_text = match.group(1)
    json_text = re.sub(r"\bxValues\s*:", '"xValues":', json_text)
    json_text = re.sub(r"\byValues\s*:", '"yValues":', json_text)
    json_text = re.sub(r",\s*}", "}", json_text)
    json_text = re.sub(r",\s*]", "]", json_text)

    try:
        data = json.loads(json_text)
        logging.info(f"Vellum: Extracted raw data with {len(data)} keys (models).")

        normalized = []

        # Iterate through all keys (models)
        for model_name, metrics_data in data.items():
            if not isinstance(metrics_data, dict):
                continue

            x_vals = metrics_data.get("xValues", [])
            y_vals = metrics_data.get("yValues", [])

            if not x_vals or not y_vals:
                continue

            # Determine which axis is metric names vs scores
            # Heuristic: Metric names are strings, scores are numbers
            # Usually xValues=Benchmarks, yValues=Scores

            # Helper to find index of a target metric
            def find_score(names, scores, targets):
                for t in targets:
                    for i, name in enumerate(names):
                        if name and isinstance(name, str) and t.lower() in name.lower():
                            return scores[i]
                return None

            # Determine axis based on first non-null element
            first_x = next((x for x in x_vals if x is not None), None)
            first_y = next((y for y in y_vals if y is not None), None)

            score = 0.0
            extracted_metrics = {}

            # Check if xValues are strings (Metrics)
            if isinstance(first_x, str):
                # Extract all metrics
                for i, name in enumerate(x_vals):
                    if name and i < len(y_vals) and isinstance(y_vals[i], (int, float)):
                        extracted_metrics[name] = y_vals[i]

                # Try to find Elo/Win Rate in xValues, get yValues
                # Prioritize: "Elo", "Win Rate", "Average", "Overall"
                val = find_score(
                    x_vals, y_vals, ["elo", "win rate", "average", "overall"]
                )
                if val is not None:
                    score = val
                else:
                    # Fallback: take average of all scores? or just first one?
                    # Let's take the first numeric value
                    for v in y_vals:
                        if isinstance(v, (int, float)):
                            score = v
                            break

            # Maybe swapped? yValues are strings?
            elif isinstance(first_y, str):
                # Extract all metrics
                for i, name in enumerate(y_vals):
                    if name and i < len(x_vals) and isinstance(x_vals[i], (int, float)):
                        extracted_metrics[name] = x_vals[i]

                val = find_score(
                    y_vals, x_vals, ["elo", "win rate", "average", "overall"]
                )
                if val is not None:
                    score = val
                else:
                    for v in x_vals:
                        if isinstance(v, (int, float)):
                            score = v
                            break

            # Ensure score is float
            try:
                score = float(score)
            except:
                score = 0.0

            normalized.append(
                {
                    "model": model_name,
                    "score": score,
                    "source": "vellum",
                    "details": {"raw_score": score, "metrics": extracted_metrics},
                }
            )

        # Sort by score descending
        normalized.sort(key=lambda x: x["score"], reverse=True)

        # Add ranks
        for i, item in enumerate(normalized, 1):
            item["rank"] = i

        logging.info(f"Vellum: Parsed {len(normalized)} models.")
        return normalized

    except json.JSONDecodeError as e:
        logging.error(f"Vellum: JSON Parse Error: {e}")
        return []


if __name__ == "__main__":
    data = scrape_vellum()
    print(json.dumps(data[:3], indent=2))
