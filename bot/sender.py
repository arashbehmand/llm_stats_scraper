import telebot
import os
import logging

def send_telegram_message(message):
    """
    Sends a message to a Telegram channel/chat using pyTelegramBotAPI.
    Expects TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in environment variables.
    Implements fallback strategy: MarkdownV2 -> Markdown -> Plain Text.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logging.error("Telegram: Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID env vars.")
        return False

    bot = telebot.TeleBot(token)

    try:
        # Try MarkdownV2
        bot.send_message(chat_id, message, parse_mode="MarkdownV2")
        logging.info("Telegram: Message sent successfully (MarkdownV2).")
        return True
    except telebot.apihelper.ApiTelegramException as e:
        logging.warning(f"Telegram: MarkdownV2 failed ({e}). Retrying with legacy Markdown...")
        try:
            # Clean up MarkdownV2 escapes that are not supported/needed in legacy Markdown
            # Legacy Markdown does not support escaping -, ., !, (, ), # with backslash
            legacy_message = message.replace(r'\-', '-').replace(r'\.', '.').replace(r'\!', '!')
            legacy_message = legacy_message.replace(r'\(', '(').replace(r'\)', ')').replace(r'\#', '#')
            legacy_message = legacy_message.replace(r'\,', ',').replace(r'\=', '=').replace(r'\|', '|')
            
            # Try Legacy Markdown
            bot.send_message(chat_id, legacy_message, parse_mode="Markdown")
            logging.info("Telegram: Message sent successfully (Legacy Markdown).")
            return True
        except telebot.apihelper.ApiTelegramException as e2:
            logging.warning(f"Telegram: Legacy Markdown failed ({e2}). Retrying with plain text...")
            try:
                # Try Plain Text
                bot.send_message(chat_id, message)
                logging.info("Telegram: Message sent successfully (Plain Text).")
                return True
            except Exception as e3:
                logging.error(f"Telegram: Failed to send message (Plain Text): {e3}")
                return False
    except Exception as e:
        logging.error(f"Telegram: Unexpected error: {e}")
        return False
