# LLM Stats Scraper Bot

A Dockerized Python application that monitors major LLM leaderboards (LMSYS Arena, Vellum, Artificial Analysis, LLMStats), detects significant market movements (new models, rank changes), and publishes AI-generated reports to a Telegram channel.

## About This Project

This project addresses the challenge of staying current with the rapidly evolving AI landscape by automating the monitoring of multiple LLM leaderboards. With new models launching weekly and rankings shifting constantly, manually tracking these changes across different platforms is time-consuming and inefficient.

### Problem & Solution

**The Challenge:** AI practitioners, researchers, and enthusiasts need to track model performance across multiple leaderboards (LMSYS Arena, Vellum, Artificial Analysis, LLMStats, OpenRouter), but each platform has different formats, update schedules, and ranking methodologies.

**The Solution:** An automated system that:
- Scrapes 5 major leaderboards hourly using adaptive parsing techniques (handling both static APIs and dynamic RSC-based endpoints)
- Applies intelligent diff logic to filter noise and identify meaningful changes (new model entries, significant rank movements, score anomalies)
- Generates human-readable "breaking news" reports using LLM-powered summarization
- Delivers updates instantly via Telegram with robust error handling and fallback mechanisms

### Technical Highlights

- **Resilient Scraping:** Handles diverse data sources including REST APIs, RSC (React Server Components) payloads, and structured JSON endpoints
- **Smart Change Detection:** Custom diff engine that distinguishes between signal (new top-10 model) and noise (minor score fluctuations)
- **Production-Grade Reliability:** Retry logic, state persistence, HTML/plain-text fallback for messages, and containerized deployment
- **LLM Observability:** Optional Langfuse integration for tracing report generation, latency monitoring, and cost analysis
- **Flexible Configuration:** Supports multiple LLM providers (OpenAI, Google Gemini, Claude) via LiteLLM with configurable thinking levels for reasoning models

### Tech Stack

- **Language:** Python 3.11+
- **LLM Framework:** LangChain + LiteLLM (provider-agnostic)
- **Messaging:** pyTelegramBotAPI
- **Observability:** Langfuse (optional)
- **Deployment:** Docker + Docker Compose
- **Testing:** pytest

### Use Cases

- Personal AI news aggregation
- Research monitoring for ML teams
- Competitive intelligence for AI companies
- Educational tool for understanding LLM benchmarking landscape

This project demonstrates end-to-end development of a production-ready data pipeline, from web scraping and state management to AI-powered content generation and reliable delivery.

## Features

- **Multi-Source Scraping**: Monitors 5 major leaderboards:
    - [LMSYS Chatbot Arena](https://chat.lmsys.org/) (Text, Vision & Code)
    - [Vellum](https://www.vellum.ai/llm-leaderboard)
    - [Artificial Analysis](https://artificialanalysis.ai/)
    - [LLMStats](https://llm-stats.com/) (via ZeroEval API)
    - [OpenRouter](https://openrouter.ai/rankings) (Weekly rankings)
- **Smart Diff Engine**: Detects meaningful changes (new entrants, significant rank swaps, score spikes) while filtering out noise.
- **AI Reporting**: Uses GPT-5 / Gemini-3-Flash (via LangChain + LiteLLM) to generate professional "Breaking News" updates.
- **Telegram Integration**: Automatically posts updates to your channel with retry logic and HTML/plain text fallback for reliability.
- **State Persistence**: Tracks history to compare against the last successful run.
- **LLM Tracing**: Optional Langfuse integration for monitoring and debugging report generation.
- **State Management Utility**: Manual state modification tool for testing and troubleshooting.

## Prerequisites

- Python 3.11+
- OpenAI/Gemini API Key (for report generation)
- Telegram Bot Token & Channel ID
- Optional: Langfuse account + API keys (for LLM tracing)

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd llm_stats_scraper
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment**:
    Copy the example environment file and fill in your details:
    ```bash
    cp .env.example .env
    ```
    Edit `.env`:
    ```ini
    TELEGRAM_TOKEN=your_bot_token_here
    TELEGRAM_CHAT_ID=@your_channel_name
    OPENAI_API_KEY=sk-...
    
    # Optional: Custom LLM configuration for report generation
    REPORTING_LLM_CONFIG={"model": "gemini/gemini-3-flash-preview", "thinking_level": "medium"}
    ```

## Usage

### Local Run
Run the main script. The first run will establish a baseline (saving state to `state/last_run.json`). Subsequent runs will compare against this state.

```bash
python main.py
```

### Docker
Build and run the container. Mount the `state` directory to persist history across container restarts.

```bash
# Build
docker build -t llm-bot .

# Run
docker run --env-file .env -v $(pwd)/state:/app/state llm-bot
```

### Docker Compose (Recommended)
Use Docker Compose to run the bot as a background service that checks for updates every hour.

1. Ensure `.env` is configured.
2. Run:
   ```bash
   docker compose up -d
   ```
   This will build the image and start the container in a loop (interval: 1 hour).
   Logs can be viewed with:
   ```bash
   docker compose logs -f
   ```

### Automation
To run hourly via cron (alternative to Docker Compose):
```bash
0 * * * * cd /path/to/llm_stats_scraper && /usr/bin/python3 main.py >> /var/log/llm_bot.log 2>&1
```

### State Management Utility
For testing or troubleshooting, you can manually modify the saved state using:
```bash
python modify_state.py
```
This utility allows you to remove specific models from the state file, useful for forcing re-detection of changes or testing diff logic.

## Customization

### Reporting LLM Model
You can customize which LLM model is used for report generation by setting the `REPORTING_LLM_CONFIG` environment variable:

```ini
REPORTING_LLM_CONFIG={"model": "gemini/gemini-3-flash-preview", "thinking_level": "medium"}
```

Supported parameters:
- `model`: Any LiteLLM-compatible model identifier (e.g., `gpt-4o`, `claude-4-5-sonnet-20250929`, `gemini/gemini-3-flash-preview`)
- `thinking_level`: For models that support extended thinking (e.g., Gemini 3.0), set to `low`, `medium`, or `high`

If not specified, defaults to `gpt-4o`.

### Reporting Prompt
You can customize the style and persona of the news reports by editing `reporting/prompt.txt`. This file contains the system prompt used by the AI News Anchor.

### Thresholds
Adjust `logic/diff.py` to change sensitivity for rank/score changes (e.g., minimum rank jump to report).

### Langfuse (Optional)
You can enable Langfuse tracing for full pipeline visibility (scraping, state loading, diff calculation, report generation) by setting:

```ini
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

Notes:
- If `LANGFUSE_ENABLED` is `false`, tracing is still enabled automatically when both Langfuse keys are present.
- If not configured, the app behavior is unchanged.

## Project Structure

```
llm_stats_scraper/
├── bot/                # Telegram messaging logic (retry + fallback)
├── logic/              # Diff engine (change detection)
├── reporting/          # LangChain + LiteLLM report generation
├── scrapers/           # Individual leaderboard scrapers (Arena, Vellum, Artificial Analysis, LLMStats, OpenRouter)
├── state/              # JSON storage for last run state
├── utils/              # Shared helpers (Langfuse integration)
├── main.py             # Entry point
├── modify_state.py     # State management utility
└── requirements.txt    # Python dependencies
```
