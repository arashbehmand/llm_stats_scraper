"""
Per-channel file-based outbox.

Each channel gets one file: state/outbox/<channel>.json
If delivery fails, the file stays. On the next run, the new message is
appended to the pending one so a single combined message is sent.
File is removed only after successful delivery.
"""

import json
import logging
import os

logger = logging.getLogger("Outbox")

OUTBOX_DIR = "state/outbox"
SEPARATOR = "\n\n---\n\n"


def _ensure_dir():
    os.makedirs(OUTBOX_DIR, exist_ok=True)


def _path(channel):
    return os.path.join(OUTBOX_DIR, f"{channel}.json")


def _read(channel):
    """Return the pending message string for a channel, or None if outbox is empty."""
    p = _path(channel)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("message")
    except Exception as exc:
        logger.error(f"Outbox [{channel}]: corrupt file, will overwrite. Error: {exc}")
        return None


def _write(channel, message):
    """Atomically write (or overwrite) the outbox file for a channel."""
    _ensure_dir()
    p = _path(channel)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"message": message}, f)
        os.replace(tmp, p)
    except Exception as exc:
        logger.error(f"Outbox [{channel}]: failed to write: {exc}")
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _remove(channel):
    p = _path(channel)
    try:
        os.remove(p)
    except FileNotFoundError:
        pass


def enqueue(channel, new_message):
    """
    Add new_message to the channel's outbox.
    If a previous unsent message exists, it is prepended so they are
    delivered together as one combined message.
    """
    pending = _read(channel)
    if pending:
        combined = pending + SEPARATOR + new_message
        logger.info(f"Outbox [{channel}]: appending to existing pending message.")
    else:
        combined = new_message
    _write(channel, combined)
    logger.info(f"Outbox [{channel}]: message enqueued.")


def drain(channel, send_fn):
    """
    Attempt to deliver the pending message for a channel.

    send_fn: callable(message_str) -> True | False | None
      True  = sent OK   → remove outbox file
      False = failed    → keep file, retry next run
      None  = not configured → remove file (no point retrying)

    Returns True if the outbox is now clear (sent or not configured),
    False if delivery failed and message is still pending.
    """
    message = _read(channel)
    if message is None:
        return True  # Nothing pending

    result = send_fn(message)

    if result is True:
        _remove(channel)
        logger.info(f"Outbox [{channel}]: delivered and cleared.")
        return True
    elif result is None:
        _remove(channel)
        logger.info(f"Outbox [{channel}]: not configured, clearing outbox.")
        return True
    else:
        logger.warning(
            f"Outbox [{channel}]: delivery failed, message retained for next run."
        )
        return False
