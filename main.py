import json
import logging
import os

from dotenv import load_dotenv

from bot.sender import send_telegram_message
from logic.diff import run_diff
from reporting.generator import generate_report
from scrapers.arena import scrape_arena
from scrapers.artificial_analysis import scrape_artificial_analysis
from scrapers.llmstats import scrape_llmstats
from scrapers.openrouter import scrape_openrouter
from scrapers.vellum import scrape_vellum
from utils.langfuse_setup import initialize_langfuse

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

STATE_FILE = "state/last_run.json"


def main():
    load_dotenv()
    logging.info("Starting LLM Stats Scraper...")

    # Initialize Langfuse
    langfuse = initialize_langfuse()
    trace = None
    if langfuse:
        trace = langfuse.trace(name="LLM Stats Scraper Run")

    # 1. Scrape All Sources
    logging.info("Scraping Arena...")

    retrieval_span = None
    if trace:
        retrieval_span = trace.span(name="Data Retrieval")

    try:
        # Helper to wrap scraping in a span
        def scrape_with_span(name, func, *args):
            if not retrieval_span:
                return func(*args)

            span = retrieval_span.span(name=f"Scrape {name}")
            try:
                result = func(*args)
                span.update(metadata={"count": len(result)})
                span.end()
                return result
            except Exception as e:
                span.update(level="ERROR", status_message=str(e))
                span.end()
                raise e

        arena_text = scrape_with_span("Arena Text", scrape_arena, "text")
        arena_vision = scrape_with_span("Arena Vision", scrape_arena, "vision")
        arena_code = scrape_with_span("Arena Code", scrape_arena, "code")

        logging.info("Scraping Vellum...")
        vellum = scrape_with_span("Vellum", scrape_vellum)

        logging.info("Scraping Artificial Analysis...")
        artificial = scrape_with_span("Artificial Analysis", scrape_artificial_analysis)

        logging.info("Scraping LLMStats...")
        llmstats = scrape_with_span("LLMStats", scrape_llmstats)

        logging.info("Scraping OpenRouter...")
        openrouter = scrape_with_span("OpenRouter", scrape_openrouter)

        if retrieval_span:
            retrieval_span.end()

    except Exception as e:
        if retrieval_span:
            retrieval_span.update(level="ERROR", status_message=str(e))
            retrieval_span.end()
        raise e

    # 2. Prepare Current State
    current_state = {
        "arena_text": arena_text,
        "arena_vision": arena_vision,
        "arena_code": arena_code,
        "vellum": vellum,
        "artificial_analysis": artificial,
        "llmstats": llmstats,
        "openrouter": openrouter,
    }

    # 3. Load Previous State
    state_span = None
    if trace:
        state_span = trace.span(name="State Loading")

    previous_state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                previous_state = json.load(f)
            logging.info(f"Loaded previous state from {STATE_FILE}")
            if state_span:
                # Count models per source in previous state
                model_counts = {
                    k: len(v) for k, v in previous_state.items() if isinstance(v, list)
                }
                state_span.update(
                    metadata={"state_loaded": True, "model_counts": model_counts}
                )
        except json.JSONDecodeError:
            logging.warning("Previous state file corrupted. Treating as empty.")
            # If corrupted, we should probably ignore it to avoid massive diff
            previous_state = {}
            if state_span:
                state_span.update(
                    metadata={"state_loaded": False, "error": "Corrupted state file"}
                )

    if not previous_state:
        # First run - just save state, don't alert
        logging.info("First run detected. Saving state and exiting.")

        if state_span:
            state_span.update(metadata={"first_run": True})
            state_span.end()

        # Storage Span for first run
        storage_span = None
        if trace:
            storage_span = trace.span(name="Data Storage")

        with open(STATE_FILE, "w") as f:
            json.dump(current_state, f, indent=2)

        if storage_span:
            storage_span.update(metadata={"action": "First run save"})
            storage_span.end()

        return

    if state_span:
        state_span.end()

    # 4. Detect Changes
    # Since detect_changes operates per source, we need to iterate or refactor it.
    # The current `detect_changes` implementation assumes `current_data` is dict of sources,
    # which matches `current_state` structure! Perfect.

    # We want to detect changes across ALL sources at once
    # However, `detect_changes` expects input like {source_name: [items]}, which is exactly what current_state is.

    diff_span = None
    if trace:
        diff_span = trace.span(name="Diff Calculation")

    diff_report = run_diff(current_state, previous_state)

    # Check if there are significant changes
    has_changes = bool(
        diff_report.get("new_entries") or diff_report.get("rank_changes")
    )

    if diff_span:
        stats = {
            "new_entries": len(diff_report.get("new_entries", [])),
            "rank_changes": len(diff_report.get("rank_changes", [])),
            "score_changes": len(diff_report.get("score_changes", [])),
            "has_significant_changes": has_changes,
        }
        diff_span.update(metadata=stats)
        diff_span.end()

    # --- Default: update state at the end of the run ---
    should_update_state = True

    if has_changes:
        logging.info(
            f"Changes detected: {len(diff_report['new_entries'])} new models, {len(diff_report['rank_changes'])} rank changes."
        )

        # 5. Generate Report
        generation_span = None
        if trace:
            generation_span = trace.span(name="Generation")
            generation_span.update(input=diff_report)

        logging.debug(f"Diff Report: {json.dumps(diff_report, indent=2)}")

        # Pass trace_id to report generator if needed, but current implementation uses global callbacks
        # We can wrap the generation call in the span context
        report_text = generate_report(diff_report, current_state)

        if generation_span:
            generation_span.update(output=report_text)
            generation_span.end()

        if report_text:
            logging.info(f"Generated Report: {report_text}...")

            # 6. Publish to Telegram
            telegram_span = None
            if trace:
                telegram_span = trace.span(name="Telegram Send")

            success = send_telegram_message(report_text)

            if success:
                logging.info("Report published successfully.")
                if telegram_span:
                    telegram_span.update(metadata={"success": True})
            else:
                logging.error(
                    "Failed to publish report. State will NOT be updated (will retry next run)."
                )
                should_update_state = False
                if telegram_span:
                    telegram_span.update(level="ERROR", metadata={"success": False})

            if telegram_span:
                telegram_span.end()
        else:
            logging.info("Changes detected but deemed insignificant by reporter.")
    else:
        logging.info("No significant changes detected.")

    # 7. Single state update point
    if should_update_state:
        storage_span = None
        if trace:
            storage_span = trace.span(name="Data Storage")

        with open(STATE_FILE, "w") as f:
            json.dump(current_state, f, indent=2)
        logging.info(f"State saved to {STATE_FILE}.")

        if storage_span:
            storage_span.update(metadata={"action": "Update state"})
            storage_span.end()
    else:
        logging.warning(
            f"State NOT updated — retaining previous {STATE_FILE} for retry."
        )


if __name__ == "__main__":
    main()
