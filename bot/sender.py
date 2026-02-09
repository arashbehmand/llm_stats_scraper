import requests
import os
import logging

def send_telegram_message(message):
    """
    Sends a message to a Telegram channel/chat.
    Expects TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in environment variables.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logging.error("Telegram: Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID env vars.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info("Telegram: Message sent successfully.")
        return True
    except Exception as e:
        logging.error(f"Telegram: Failed to send message: {e}")
        return False
