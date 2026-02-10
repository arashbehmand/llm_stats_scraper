import logging
import os
import time

import telebot

MDV2_RESERVED_CHARS = r"_*[]()~`>#+-=|{}.!"


def _send_with_retries(bot, chat_id, text, parse_mode=None, retries=3, delay_seconds=2):
    """
    Minimal retry loop for transient Telegram/network errors.
    """
    for attempt in range(1, retries + 1):
        try:
            if parse_mode:
                bot.send_message(chat_id, text, parse_mode=parse_mode)
            else:
                bot.send_message(chat_id, text)
            return True
        except Exception as e:
            if attempt == retries:
                raise
            logging.warning(
                f"Telegram: send attempt {attempt}/{retries} failed ({e}). Retrying..."
            )
            time.sleep(delay_seconds)


def send_telegram_message(message):
    """
    Sends a message to a Telegram channel/chat using pyTelegramBotAPI.
    Expects TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in environment variables.
    Uses HTML parse mode for reliability.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logging.error("Telegram: Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID env vars.")
        return False

    bot = telebot.TeleBot(token)

    try:
        # Try HTML
        _send_with_retries(bot, chat_id, message, parse_mode="HTML")
        logging.info("Telegram: Message sent successfully (HTML).")
        return True
    except telebot.apihelper.ApiTelegramException as e:
        logging.warning(f"Telegram: HTML failed ({e}). Retrying with plain text...")
        try:
            # Fallback: Plain Text (strip tags approximately or just send raw)
            # Sending raw allows reading the text even if tags are broken
            _send_with_retries(bot, chat_id, message)
            logging.info("Telegram: Message sent successfully (Plain Text / Raw).")
            return True
        except Exception as e3:
            logging.error(f"Telegram: Failed to send message (Plain Text): {e3}")
            return False
    except Exception as e:
        logging.error(f"Telegram: Unexpected error: {e}")
        return False
