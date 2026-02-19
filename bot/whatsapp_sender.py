import html
import logging
import os
import re
import time

import requests

logger = logging.getLogger("WhatsAppSender")


def _headers():
    token = os.environ.get("WHAPI_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def telegram_html_to_whatsapp(text):
    """Convert Telegram HTML to WhatsApp-compatible plain text with basic formatting."""
    if not text:
        return ""
    s = text
    s = re.sub(
        r'<a\s+href="([^"]+)">(.*?)</a>', r"\2 (\1)", s, flags=re.IGNORECASE | re.DOTALL
    )
    s = re.sub(r"<b>(.*?)</b>", r"*\1*", s, flags=re.DOTALL)
    s = re.sub(r"<i>(.*?)</i>", r"_\1_", s, flags=re.DOTALL)
    s = re.sub(r"<code>(.*?)</code>", r"`\1`", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def send_whatsapp_message(message):
    """
    Send a message (Telegram HTML) to a WhatsApp channel via Whapi gateway.

    Returns True on success, False on failure, None if not configured.
    """
    api_url = (os.environ.get("WHAPI_API_URL") or "").rstrip("/")
    token = os.environ.get("WHAPI_TOKEN", "").strip()
    jid = os.environ.get("WHATSAPP_CHANNEL_JID", "").strip()

    if not api_url or not token:
        logger.debug(
            "WhatsApp: not configured (missing WHAPI_API_URL or WHAPI_TOKEN). Skipping."
        )
        return None

    if not jid:
        logger.error("WhatsApp: WHATSAPP_CHANNEL_JID not set.")
        return False

    plain_text = telegram_html_to_whatsapp(message)
    endpoint = f"{api_url}/messages/text"
    payload = {"to": jid, "body": plain_text, "typing_time": 0}

    for attempt in range(1, 4):
        try:
            resp = requests.post(endpoint, headers=_headers(), json=payload, timeout=30)
            resp.raise_for_status()
            logger.info(
                f"WhatsApp: sent successfully (id={resp.json().get('sent_id', 'N/A')})"
            )
            return True
        except Exception as exc:
            if attempt == 3:
                logger.error(f"WhatsApp: all 3 attempts failed: {exc}")
                return False
            logger.warning(f"WhatsApp: attempt {attempt}/3 failed ({exc}). Retrying...")
            time.sleep(2)
    return False
