"""
Ntfy integration: a background subscriber that listens for messages on the
configured topic and holds the latest one (with a 10-minute expiry) for
/api/matrix to include as a bottom banner - plus a send-side helper used
for the automatic emergency-squawk alert.
"""
import json
import logging
import threading
import time

import requests

log = logging.getLogger("skywatch.ntfy")

NTFY_BASE = "https://ntfy.sh"  # override to your own instance if self-hosted
BANNER_DURATION_SECONDS = 10 * 60

_lock = threading.Lock()
_banner = {"text": None, "expires_at": 0}
_subscriber_thread = None
_subscriber_topic = None


def current_banner():
    """Returns (text, expires_at_epoch) if a banner is currently active,
    else (None, None). Callers should not need to check expiry themselves."""
    with _lock:
        if _banner["text"] and time.time() < _banner["expires_at"]:
            return _banner["text"], _banner["expires_at"]
        return None, None


def _set_banner(text):
    with _lock:
        _banner["text"] = text
        _banner["expires_at"] = time.time() + BANNER_DURATION_SECONDS
    log.info("ntfy banner set, expires in %ds: %s", BANNER_DURATION_SECONDS, text)


def send_message(topic, title, message, priority="urgent"):
    """Send an outbound ntfy notification - used for the emergency-squawk
    alert. This is independent of the subscriber loop below."""
    if not topic:
        return
    try:
        requests.post(
            f"{NTFY_BASE}/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority},
            timeout=5,
        )
    except Exception as e:
        log.warning("Failed to send ntfy alert: %s", e)


def _subscribe_loop(topic):
    """Long-lived SSE connection to ntfy's topic stream. Reconnects on any
    failure with a short backoff - this must never crash the thread."""
    url = f"{NTFY_BASE}/{topic}/sse"
    while True:
        try:
            with requests.get(url, stream=True, timeout=(5, None)) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8")
                    if not line.startswith("data:"):
                        continue
                    try:
                        payload = json.loads(line[len("data:"):].strip())
                    except json.JSONDecodeError:
                        continue
                    if payload.get("event") != "message":
                        continue
                    text = payload.get("message", "")
                    if text:
                        _set_banner(text)
        except Exception as e:
            log.warning("ntfy subscribe connection dropped, retrying in 10s: %s", e)
        time.sleep(10)


def start_subscriber(topic):
    """(Re)start the background subscriber if the topic changed. Safe to
    call repeatedly (e.g. every time admin settings are saved) - it only
    spins up a new thread when the topic is actually different."""
    global _subscriber_thread, _subscriber_topic
    if not topic:
        return
    if _subscriber_thread and _subscriber_thread.is_alive() and _subscriber_topic == topic:
        return  # already running for this topic
    _subscriber_topic = topic
    _subscriber_thread = threading.Thread(target=_subscribe_loop, args=(topic,), daemon=True)
    _subscriber_thread.start()
    log.info("Started ntfy subscriber for topic '%s'", topic)
