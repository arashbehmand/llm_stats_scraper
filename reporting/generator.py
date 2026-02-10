import json
import logging
import os

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_litellm import ChatLiteLLM

METRIC_CANDIDATE_KEYS = [
    "elo",
    "rating",
    "score",
    "overall",
    "quality_index",
    "intelligence_index",
    "gpqa",
    "gpqa_diamond",
    "mmlu",
    "mmlu_pro",
    "aime_24",
    "aime_25",
    "math_index",
    "math_500",
    "livecodebench",
    "swe_bench",
    "humanitys_last_exam",
    "p50_latency",
    "p50_throughput",
    "provider_count",
    "request_count",
    "usage_share_pct",
    "usage_metric_key",
]


def _to_csv_cell(value):
    text = str(value) if value is not None else ""
    text = text.replace("\n", " ").replace("\r", " ").replace(",", ";")
    return text


def _extract_metrics(details, max_items=5):
    if not isinstance(details, dict):
        return []

    selected = []
    used = set()

    for key in METRIC_CANDIDATE_KEYS:
        if key in details:
            val = details.get(key)
            if isinstance(val, (int, float, str)):
                selected.append((key, val))
                used.add(key)
            if len(selected) >= max_items:
                return selected

    for key, val in details.items():
        if key in used:
            continue
        if isinstance(val, (int, float)):
            selected.append((key, val))
            if len(selected) >= max_items:
                break
    return selected


def _format_metrics_inline(details):
    metrics = _extract_metrics(details)
    if not metrics:
        return "-"
    return " | ".join([f"{k}={v}" for k, v in metrics])


def _format_changes_markdown(diff_report):
    lines = []

    def add_block(change_type, change):
        lines.append(f"### {change_type}")
        lines.append(f"Source: {change.get('source', 'unknown')}")
        lines.append(f"Model: {change.get('model', 'unknown')}")

        if change_type == "new_entry":
            lines.append(f"Rank: {change.get('rank')}")
            lines.append(f"Score: {change.get('score')}")
        elif change_type == "rank_change":
            lines.append(f"Old Rank: {change.get('old_rank')}")
            lines.append(f"New Rank: {change.get('new_rank')}")
            lines.append(f"Score: {change.get('score')}")
            lines.append(f"Rank Delta: {change.get('change')}")
        elif change_type == "score_change":
            lines.append(f"Old Score: {change.get('old_score')}")
            lines.append(f"New Score: {change.get('new_score')}")
            lines.append(f"Score Delta: {change.get('diff')}")

        context = change.get("context")
        if context:
            lines.append(f"Context: {context}")

        lines.append(f"Metrics: {_format_metrics_inline(change.get('details', {}))}")
        lines.append("")

    for change in diff_report.get("new_entries", []):
        add_block("new_entry", change)
    for change in diff_report.get("rank_changes", []):
        add_block("rank_change", change)
    for change in diff_report.get("score_changes", []):
        add_block("score_change", change)

    if not lines:
        return "No changes."
    return "\n".join(lines).strip()


def generate_report(diff_report, current_state=None):
    """
    Generates a breaking news report using LangChain and LiteLLM.
    """
    llm_config_str = os.environ.get("REPORTING_LLM_CONFIG")
    if not llm_config_str:
        logging.error("Reporting: Missing REPORTING_LLM_CONFIG in .env.")
        return None

    try:
        llm_config = json.loads(llm_config_str)
    except json.JSONDecodeError:
        logging.error("Reporting: Invalid JSON in REPORTING_LLM_CONFIG.")
        return None

    if not diff_report.get("new_entries") and not diff_report.get("rank_changes"):
        logging.info("Reporting: No significant changes to report.")
        return None

    # Best-effort observability; no-op unless Langfuse env is configured.
    # initialize_langfuse() # Already initialized in main.py

    # Load external prompt
    try:
        with open("reporting/prompt.txt", "r") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        logging.warning("Reporting: prompt.txt not found, using fallback.")
        system_prompt = "You are an AI News Anchor. Report these changes: {changes}"

    # Prepare Context (Top 10 models per source + key metrics)
    context_lines = []
    if current_state:
        for source, models in current_state.items():
            # Ensure models is a list
            if not isinstance(models, list):
                continue

            # Filter out None/empty
            valid_models = [m for m in models if isinstance(m, dict)]

            if not valid_models:
                continue

            # Add Header for this Source
            context_lines.append(f"\nSource: {source.upper()}")
            context_lines.append("Rank,Model,Score,Metrics")

            # Take top 10
            for m in valid_models[:10]:
                try:
                    score = m.get("score", 0)
                    if isinstance(score, float):
                        score = f"{score:.2f}"

                    metrics = _format_metrics_inline(m.get("details", {}))
                    line = ",".join(
                        [
                            _to_csv_cell(m.get("rank")),
                            _to_csv_cell(m.get("model")),
                            _to_csv_cell(score),
                            _to_csv_cell(metrics),
                        ]
                    )
                    context_lines.append(line)
                except:
                    continue

    csv_context = "\n".join(context_lines)

    # Prepare changes as markdown paragraphs (one block per detected change).
    markdown_changes = _format_changes_markdown(diff_report)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            (
                "user",
                "CONTEXT (CSV):\n```csv\n{context}\n```\n\nCHANGES (MARKDOWN):\n```markdown\n{changes}\n```",
            ),
        ]
    )

    # Initialize ChatLiteLLM with config from JSON
    # We extract 'model' as it's a required positional/keyword arg for ChatLiteLLM usually,
    # but passing **llm_config works if 'model' is in the dict.
    # Note: ChatLiteLLM expects 'model' to be specified.
    if "model" not in llm_config:
        logging.error("Reporting: 'model' key missing in REPORTING_LLM_CONFIG.")
        return None

    try:
        llm = ChatLiteLLM(**llm_config)
        chain = prompt | llm | StrOutputParser()

        report = chain.invoke({"context": csv_context, "changes": markdown_changes})

        # Post-processing (length check only)
        if len(report) > 4000:
            report = report[:4000] + "...\n(Report truncated)"

        logging.info("Reporting: Generated update.")
        return report
    except Exception as e:
        logging.error(f"Reporting: LLM failed: {e}")
        return None
