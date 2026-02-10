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

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

STATE_FILE = "state/last_run.json"


def main():
    load_dotenv()
    logging.info("Starting LLM Stats Scraper...")

    # 1. Scrape All Sources
    logging.info("Scraping Arena...")
    arena_text = scrape_arena("text")
    arena_vision = scrape_arena("vision")
    arena_code = scrape_arena("code")

    logging.info("Scraping Vellum...")
    vellum = scrape_vellum()

    logging.info("Scraping Artificial Analysis...")
    artificial = scrape_artificial_analysis()

    logging.info("Scraping LLMStats...")
    llmstats = scrape_llmstats()

    logging.info("Scraping OpenRouter...")
    openrouter = scrape_openrouter()

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
    previous_state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                previous_state = json.load(f)
            logging.info(f"Loaded previous state from {STATE_FILE}")
        except json.JSONDecodeError:
            logging.warning("Previous state file corrupted. Treating as empty.")
            # If corrupted, we should probably ignore it to avoid massive diff
            previous_state = {}

    if not previous_state:
        # First run - just save state, don't alert
        logging.info("First run detected. Saving state and exiting.")
        with open(STATE_FILE, "w") as f:
            json.dump(current_state, f, indent=2)
        return

    # 4. Detect Changes
    # Since detect_changes operates per source, we need to iterate or refactor it.
    # The current `detect_changes` implementation assumes `current_data` is dict of sources,
    # which matches `current_state` structure! Perfect.

    # We want to detect changes across ALL sources at once
    # However, `detect_changes` expects input like {source_name: [items]}, which is exactly what current_state is.

    diff_report = run_diff(current_state, previous_state)

    # Check if there are significant changes
    has_changes = bool(
        diff_report.get("new_entries") or diff_report.get("rank_changes")
    )

    # --- Default: update state at the end of the run ---
    should_update_state = True

    if has_changes:
        logging.info(
            f"Changes detected: {len(diff_report['new_entries'])} new models, {len(diff_report['rank_changes'])} rank changes."
        )

        # 5. Generate Report
        logging.debug(f"Diff Report: {json.dumps(diff_report, indent=2)}")
        report_text = generate_report(diff_report, current_state)

        if report_text:
            logging.info(f"Generated Report: {report_text}...")

            # 6. Publish to Telegram
            success = send_telegram_message(report_text)

            if success:
                logging.info("Report published successfully.")
            else:
                logging.error(
                    "Failed to publish report. State will NOT be updated (will retry next run)."
                )
                should_update_state = False
        else:
            logging.info("Changes detected but deemed insignificant by reporter.")
    else:
        logging.info("No significant changes detected.")

    # 7. Single state update point
    if should_update_state:
        with open(STATE_FILE, "w") as f:
            json.dump(current_state, f, indent=2)
        logging.info(f"State saved to {STATE_FILE}.")
    else:
        logging.warning(
            f"State NOT updated — retaining previous {STATE_FILE} for retry."
        )


if __name__ == "__main__":
    main()
