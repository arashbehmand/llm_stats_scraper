"""
Multi-channel publisher with per-channel file-based outbox.

Adding a new channel: add one entry to PUBLISHERS and one name to PUBLISH_TARGETS env var.
"""

import logging
import os

from bot import outbox
from bot.sender import send_telegram_message
from bot.whatsapp_sender import send_whatsapp_message

logger = logging.getLogger("Publisher")

# Registry: channel_name -> send_function
# Each function must accept a message str and return True | False | None.
PUBLISHERS = {
    "telegram": send_telegram_message,
    "whatsapp": send_whatsapp_message,
}


def _enabled_targets():
    raw = os.getenv("PUBLISH_TARGETS", "telegram")
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def publish_report(report_html):
    """
    Enqueue report in each enabled channel's outbox, then attempt immediate delivery.
    State should always be saved after this (message is safely on disk).
    Returns True unconditionally so the caller updates state.
    """
    for channel in _enabled_targets():
        outbox.enqueue(channel, report_html)
        send_fn = PUBLISHERS.get(channel)
        if send_fn is None:
            logger.warning(
                f"Publisher: no sender registered for '{channel}', message queued for manual intervention."
            )
            continue
        outbox.drain(channel, send_fn)
    return True


def drain_all_outboxes():
    """
    Retry all pending outbox messages. Call this at startup to recover from
    previous failed deliveries.
    """
    for channel, send_fn in PUBLISHERS.items():
        outbox.drain(channel, send_fn)
