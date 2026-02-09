# CLAUDE.md - Developer Guide

## Commands
- **Run Full Process**: `python main.py`
- **Run Specific Scraper**: `python -m scrapers.arena`
- **Docker Build**: `docker build -t llm-bot .`
- **Docker Run**: `docker run -v $(pwd)/state:/app/state --env-file .env llm-bot`

## Guidelines
- **No Classes**: Use simple functions. Return standard Python types (dict, list).
- **Flat Data**: All scrapers must return a list of dicts.
- **Normalization**: Ensure `model` (name) and `rank` are always present. Keep everything else in `details`.
- **State**: `last_run.json` is the source of truth.
- **Error Handling**: If a scraper fails, log it and continue. Don't stop the whole process.
- **Vellum**: Use static analysis (regex on HTML), NO Playwright.
