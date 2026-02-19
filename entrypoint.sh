#!/bin/bash
set -e

echo "Starting LLM Stats Scraper with cron scheduling..."

# Create log file for cron output
touch /var/log/cron.log

# Load the crontab
crontab /app/crontab

echo "Cron schedule loaded:"
crontab -l

# Start cron in foreground mode and tail the log
echo "Starting cron daemon..."
cron

# Tail the cron log to keep container running and show output
echo "Monitoring cron jobs (logs will appear below)..."
tail -f /var/log/cron.log
