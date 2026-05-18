import json
import logging
import re
from html import unescape

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

BENCHMARK_FIELDS = {
    "gpqaReasoningNum": "GPQA Diamond",
    "numAime2025MathCompetition": "AIME 2025",
    "humanevalCodingNum": "SWE Bench",
    "numHumanitySLastExam": "Humanity's Last Exam",
    "numArcAgi2": "ARC-AGI 2",
    "numMmmluMultilingualQA": "MMMLU",
    "numBfclToolUse": "BFCL",
    "mathNum": "MATH 500",
    "numLiveCodebenchCodeGeneration": "LiveCodeBench",
    "numAiderPolyglot": "Aider Polyglot",
    "numGrind": "GRIND",
}


def _extract_json_array_after(text, marker):
    marker_pos = text.find(marker)
    if marker_pos == -1:
        return None

    start = text.find("[", marker_pos + len(marker))
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(text[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def _next_flight_strings(html_content):
    pattern = re.compile(r"self\.__next_f\.push\((.*?)\)</script>", re.DOTALL)
    for match in pattern.finditer(html_content):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, list)
            and len(payload) > 1
            and isinstance(payload[1], str)
        ):
            yield payload[1]


def _extract_models_from_next_flight(html_content):
    for flight in _next_flight_strings(html_content):
        array_text = _extract_json_array_after(flight, '"models":')
        if not array_text:
            continue
        try:
            models = json.loads(array_text)
        except json.JSONDecodeError:
            continue
        if isinstance(models, list) and any(
            isinstance(m, dict) and m.get("title") for m in models
        ):
            return models
    return []


def _strip_html(value):
    value = re.sub(r"<.*?>", "", value, flags=re.DOTALL)
    return unescape(value).strip()


def _score_text_to_float(value):
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group(0)) if match else None


def _extract_models_from_benchmark_tables(html_content):
    by_model = {}
    table_pattern = re.compile(r"<table[^>]*>(.*?)</table>", re.DOTALL | re.IGNORECASE)
    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    cell_pattern = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)

    for table_match in table_pattern.finditer(html_content):
        table = table_match.group(1)
        caption_match = re.search(
            r"<caption[^>]*>(.*?)</caption>", table, re.DOTALL | re.IGNORECASE
        )
        if not caption_match:
            continue
        metric = _strip_html(caption_match.group(1))
        for row in row_pattern.findall(table)[1:]:
            cells = [_strip_html(cell) for cell in cell_pattern.findall(row)]
            if len(cells) < 2:
                continue
            score = _score_text_to_float(cells[1])
            if score is None:
                continue
            by_model.setdefault(cells[0], {})[metric] = score

    return [
        {"title": model, "benchmarkMetrics": metrics}
        for model, metrics in by_model.items()
    ]


def _metrics_for_model(model):
    if "benchmarkMetrics" in model:
        metrics = model["benchmarkMetrics"]
    else:
        metrics = {
            label: model[key]
            for key, label in BENCHMARK_FIELDS.items()
            if isinstance(model.get(key), (int, float))
        }
    if not metrics:
        return 0.0, {}
    return sum(metrics.values()) / len(metrics), metrics


def _normalize_models(models):
    normalized = []
    for model in models:
        if not isinstance(model, dict):
            continue
        model_name = model.get("title") or model.get("name")
        if not model_name:
            continue

        score, metrics = _metrics_for_model(model)
        normalized.append(
            {
                "model": model_name,
                "score": float(score),
                "source": "vellum",
                "details": {
                    **model,
                    "raw_score": float(score),
                    "metrics": metrics,
                },
            }
        )

    normalized.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(normalized, 1):
        item["rank"] = i
    return normalized


def scrape_vellum():
    """
    Scrapes the current static Vellum LLM Leaderboard page.
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

    next_models = _extract_models_from_next_flight(html_content)
    if next_models:
        normalized = _normalize_models(next_models)
        logging.info(f"Vellum: Parsed {len(normalized)} models from Next data.")
        return normalized

    table_models = _extract_models_from_benchmark_tables(html_content)
    if table_models:
        normalized = _normalize_models(table_models)
        logging.info(f"Vellum: Parsed {len(normalized)} models from HTML tables.")
        return normalized

    logging.error("Vellum: Could not find current leaderboard data in HTML.")
    return []


if __name__ == "__main__":
    data = scrape_vellum()
    print(json.dumps(data[:3], indent=2))
