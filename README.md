# LLM Stats Scraper Bot

A Dockerized Python application that monitors major LLM leaderboards (LMSYS Arena, Vellum, Artificial Analysis, LLMStats), detects significant market movements (new models, rank changes), and publishes AI-generated reports to a Telegram channel.

## Features

- **Multi-Source Scraping**: Monitors 4 major leaderboards:
    - [LMSYS Chatbot Arena](https://chat.lmsys.org/) (Text & Vision)
    - [Vellum](https://www.vellum.ai/llm-leaderboard)
    - [Artificial Analysis](https://artificialanalysis.ai/)
    - [LLMStats](https://llm-stats.com/) (via ZeroEval API)
- **Smart Diff Engine**: Detects meaningful changes (new entrants, significant rank swaps, score spikes) while filtering out noise.
- **AI Reporting**: Uses GPT-4o (via LangChain) to generate professional "Breaking News" updates.
- **Telegram Integration**: Automatically posts updates to your channel.
- **State Persistence**: Tracks history to compare against the last successful run.

## Prerequisites

- Python 3.11+
- OpenAI API Key (for report generation)
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

## Customization

### Reporting Prompt
You can customize the style and persona of the news reports by editing `reporting/prompt.txt`. This file contains the system prompt used by the AI News Anchor.

### Thresholds
Adjust `logic/diff.py` to change sensitivity for rank/score changes (e.g., minimum rank jump to report).

### Langfuse (Optional)
You can enable Langfuse tracing for report generation calls (LiteLLM) by setting:

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
├── bot/                # Telegram messaging logic
├── logic/              # Diff engine (change detection)
├── reporting/          # LangChain report generation
├── scrapers/           # Individual leaderboard scrapers
├── state/              # JSON storage for last run state
├── utils/              # Shared helpers (including Langfuse bootstrap)
├── main.py             # Entry point
└── requirements.txt    # Python dependencies
```
