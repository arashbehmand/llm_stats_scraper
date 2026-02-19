import json
import logging
import os
from contextlib import contextmanager

from dotenv import load_dotenv

from bot.publish import drain_all_outboxes, publish_report
from logic.diff import run_diff
from reporting.generator import generate_report
from scrapers.arena import scrape_arena
from scrapers.artificial_analysis import scrape_artificial_analysis
from scrapers.llmstats import scrape_llmstats
from scrapers.openrouter import scrape_openrouter
from scrapers.vellum import scrape_vellum
from utils.langfuse_setup import initialize_langfuse

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

STATE_FILE = "state/last_run.json"

SCRAPERS = [
    ("arena_text", scrape_arena, ("text",)),
    ("arena_vision", scrape_arena, ("vision",)),
    ("arena_code", scrape_arena, ("code",)),
    ("vellum", scrape_vellum, ()),
    ("artificial_analysis", scrape_artificial_analysis, ()),
    ("llmstats", scrape_llmstats, ()),
    ("openrouter", scrape_openrouter, ()),
]


# ---------------------------------------------------------------------------
# Langfuse helpers
# ---------------------------------------------------------------------------


@contextmanager
def _span(parent, name):
    """Yield a Langfuse span if *parent* is truthy, otherwise yield None."""
    if not parent:
        yield None
        return
    span = parent.span(name=name)
    try:
        yield span
    finally:
        span.end()


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def run_scrapers(trace):
    """Run every scraper and return the current-state dict."""
    current_state = {}
    with _span(trace, "Data Retrieval") as retrieval:
        for name, func, args in SCRAPERS:
            logging.info(f"Scraping {name}...")
            with _span(retrieval, f"Scrape {name}") as sp:
                result = func(*args)
                if sp:
                    sp.update(metadata={"count": len(result)})
                current_state[name] = result
    return current_state


def load_state(path):
    """Load previous run state from JSON, returning {} on missing/corrupt file."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            state = json.load(f)
        logging.info(f"Loaded previous state from {path}")
        return state
    except json.JSONDecodeError:
        logging.warning("Previous state file corrupted. Treating as empty.")
        return {}


def save_state(path, data):
    """Persist current state to JSON."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logging.info(f"State saved to {path}.")


def report_and_publish(diff_report, current_state, trace):
    """Generate an LLM report and enqueue it for all configured channels.

    Always returns True — the report is durably saved to outbox before any
    delivery attempt, so state should always be updated.
    """
    logging.info(
        f"Changes detected: {len(diff_report['new_entries'])} new models, "
        f"{len(diff_report['rank_changes'])} rank changes."
    )

    langfuse_ctx = {"existing_trace_id": trace.id} if trace else None
    report_text = generate_report(diff_report, current_state, langfuse_ctx)

    if not report_text:
        logging.info("Changes detected but deemed insignificant by reporter.")
        return True

    logging.info(f"Generated Report: {report_text}...")
    with _span(trace, "Publish") as pub_sp:
        publish_report(report_text)
        if pub_sp:
            pub_sp.update(metadata={"queued": True})

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    load_dotenv()
    logging.info("Starting LLM Stats Scraper...")

    # Retry any messages that failed to deliver in the previous run
    drain_all_outboxes()

    langfuse = initialize_langfuse()
    trace = langfuse.trace(name="LLM Stats Scraper Run") if langfuse else None

    # 1. Scrape all sources
    current_state = run_scrapers(trace)

    # 2. Load previous state
    previous_state = load_state(STATE_FILE)

    if not previous_state:
        logging.info("First run detected. Saving state and exiting.")
        save_state(STATE_FILE, current_state)
        return

    # 3. Detect changes
    with _span(trace, "Diff Calculation") as diff_sp:
        diff_report = run_diff(current_state, previous_state)
        has_changes = bool(
            diff_report.get("new_entries") or diff_report.get("rank_changes")
        )
        if diff_sp:
            diff_sp.update(
                metadata={
                    "new_entries": len(diff_report.get("new_entries", [])),
                    "rank_changes": len(diff_report.get("rank_changes", [])),
                    "score_changes": len(diff_report.get("score_changes", [])),
                    "has_significant_changes": has_changes,
                }
            )

    # 4. Report, publish & persist state
    if has_changes:
        should_update = report_and_publish(diff_report, current_state, trace)
    else:
        logging.info("No significant changes detected.")
        should_update = True

    if should_update:
        save_state(STATE_FILE, current_state)
    else:
        logging.warning(
            f"State NOT updated — retaining previous {STATE_FILE} for retry."
        )


if __name__ == "__main__":
    main()
