import json
import logging
import os
import re
from datetime import datetime, timezone

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
    return text.replace("\n", " ").replace("\r", " ").replace(",", ";")


def _extract_metrics(details, max_items=5):
    if not isinstance(details, dict):
        return []

    selected = []
    used = set()

    for key in METRIC_CANDIDATE_KEYS:
        if key in details and isinstance(details[key], (int, float, str)):
            selected.append((key, details[key]))
            used.add(key)
            if len(selected) >= max_items:
                return selected

    for key, val in details.items():
        if key not in used and isinstance(val, (int, float)):
            selected.append((key, val))
            if len(selected) >= max_items:
                break
    return selected


def _format_metrics_inline(details):
    metrics = _extract_metrics(details)
    if not metrics:
        return "-"
    return " | ".join(f"{k}={v}" for k, v in metrics)


def _format_changes_markdown(diff_report):
    lines = []

    def add_block(change_type, change):
        lines.append(f"### {change_type}")
        lines.append(f"Source: {change.get('source', 'unknown')}")
        lines.append(f"Model: {change.get('model', 'unknown')}")

        if change_type == "new_entry":
            lines.append(f"Rank: {change.get('rank')}")
            lines.append(f"Score: {change.get('score')}")
            if change.get("entry_type"):
                lines.append(f"Entry Type: {change.get('entry_type')}")
            if change.get("variant_of"):
                lines.append(f"Variant Of: {change.get('variant_of')}")
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


def _load_llm_config():
    """Parse REPORTING_LLM_CONFIG from env. Returns dict or None on failure."""
    raw = os.environ.get("REPORTING_LLM_CONFIG")
    if not raw:
        logging.error("Reporting: Missing REPORTING_LLM_CONFIG in .env.")
        return None
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        logging.error("Reporting: Invalid JSON in REPORTING_LLM_CONFIG.")
        return None
    if "model" not in config:
        logging.error("Reporting: 'model' key missing in REPORTING_LLM_CONFIG.")
        return None
    return config


def _build_csv_context(current_state):
    """Format top-10 models per source as CSV for the LLM prompt."""
    context_lines = []
    if not current_state:
        return ""

    for source, models in current_state.items():
        if not isinstance(models, list):
            continue

        valid_models = [m for m in models if isinstance(m, dict)]
        if not valid_models:
            continue

        valid_models.sort(
            key=lambda row: (
                (
                    row.get("rank")
                    if isinstance(row.get("rank"), (int, float))
                    else float("inf")
                ),
                str(row.get("model", "")),
            )
        )

        context_lines.append(f"\nSource: {source.upper()}")
        context_lines.append("Rank,Model,Score,Metrics")

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
            except Exception:
                continue

    return "\n".join(context_lines)


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_model_year(model_name):
    if not model_name:
        return None
    years = re.findall(r"(20\d{2})", str(model_name))
    if not years:
        return None
    try:
        return max(int(y) for y in years)
    except ValueError:
        return None


def _is_legacy_model(model_name):
    year = _extract_model_year(model_name)
    if not year:
        return False
    current_year = datetime.now(timezone.utc).year
    return year <= (current_year - 1)


def _build_prompt_signals(diff_report, current_state):
    lines = []
    new_entries = diff_report.get("new_entries", [])
    rank_changes = diff_report.get("rank_changes", [])

    new_entry_ranks = {}
    for entry in new_entries:
        source = entry.get("source")
        rank = _to_int(entry.get("rank"), 0)
        if not source or rank <= 0:
            continue
        new_entry_ranks.setdefault(source, []).append(rank)

    if new_entry_ranks:
        lines.append("- new_entries_by_source:")
        for source, ranks in sorted(new_entry_ranks.items()):
            ranks_text = ", ".join(str(r) for r in sorted(ranks))
            lines.append(f"  - {source}: inserted_ranks={ranks_text}")
    else:
        lines.append("- new_entries_by_source: none")

    mechanical_candidates = []
    low_priority_drops = []
    for change in rank_changes:
        if _to_int(change.get("change"), 0) >= 0:
            continue
        source = change.get("source")
        model = change.get("model")
        old_rank = _to_int(change.get("old_rank"), 0)
        new_rank = _to_int(change.get("new_rank"), 0)

        inserted = sum(
            1 for rank in new_entry_ranks.get(source, []) if rank <= old_rank
        )
        expected_rank = old_rank + inserted
        residual_drop = new_rank - expected_rank

        if residual_drop <= 1:
            mechanical_candidates.append(f"{source}:{model}")
            continue

        if old_rank > 10 and new_rank > 10:
            low_priority_drops.append(f"{source}:{model} (lower-table)")
            continue

        if _is_legacy_model(model) and new_rank > 8:
            low_priority_drops.append(f"{source}:{model} (legacy)")

    if mechanical_candidates:
        lines.append(
            "- mechanical_drop_candidates: " + ", ".join(mechanical_candidates[:10])
        )
    else:
        lines.append("- mechanical_drop_candidates: none")

    if low_priority_drops:
        lines.append("- low_priority_drops: " + ", ".join(low_priority_drops[:10]))
    else:
        lines.append("- low_priority_drops: none")

    openrouter_rows = (current_state or {}).get("openrouter", [])
    if isinstance(openrouter_rows, list) and openrouter_rows:
        ranked = [row for row in openrouter_rows if isinstance(row, dict)]
        ranked.sort(
            key=lambda row: (
                -float(row.get("details", {}).get("usage_value", 0.0)),
                str(row.get("model", "")),
            )
        )
        top = ranked[0] if ranked else None
        if top:
            model = top.get("model", "unknown")
            usage_share = top.get("details", {}).get(
                "usage_share_pct", top.get("score")
            )
            usage_value = top.get("details", {}).get("usage_value", "?")
            rank = _to_int(top.get("rank"), 0)
            lines.append(
                f"- openrouter_top_by_usage: {model} "
                f"(rank={rank}, usage_share_pct={usage_share}, usage_value={usage_value})"
            )
    else:
        lines.append("- openrouter_top_by_usage: unavailable")

    return "\n".join(lines)


def generate_report(
    diff_report, current_state=None, langfuse_context=None, history_context=""
):
    """Generate a breaking-news report using LangChain and LiteLLM."""
    if not diff_report.get("new_entries") and not diff_report.get("rank_changes"):
        logging.info("Reporting: No significant changes to report.")
        return None

    llm_config = _load_llm_config()
    if not llm_config:
        return None

    try:
        with open("reporting/prompt.txt", "r") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        logging.warning("Reporting: prompt.txt not found, using fallback.")
        system_prompt = "You are an AI News Anchor. Report these changes: {changes}"

    csv_context = _build_csv_context(current_state)
    markdown_changes = _format_changes_markdown(diff_report)
    derived_signals = _build_prompt_signals(diff_report, current_state)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            (
                "user",
                "CONTEXT (CSV):\n```csv\n{context}\n```\n\nHISTORY (BASELINE+DIFF):\n```text\n{history}\n```\n\nSIGNALS (DERIVED):\n```text\n{signals}\n```\n\nCHANGES (MARKDOWN):\n```markdown\n{changes}\n```",
            ),
        ]
    )

    try:
        if langfuse_context:
            llm_config.setdefault("model_kwargs", {})["metadata"] = langfuse_context
        llm = ChatLiteLLM(**llm_config)
        chain = prompt | llm | StrOutputParser()
        report = chain.invoke(
            {
                "context": csv_context,
                "history": history_context or "-",
                "signals": derived_signals or "-",
                "changes": markdown_changes,
            }
        )

        # Check if LLM determined there are no significant updates
        if report and "no significant" in report.lower() and len(report) < 30:
            logging.info("Reporting: LLM determined no significant updates.")
            return None

        if len(report) > 4000:
            report = report[:4000] + "...\n(Report truncated)"

        logging.info("Reporting: Generated update.")
        return report
    except Exception as e:
        logging.error(f"Reporting: LLM failed: {e}")
        return None
