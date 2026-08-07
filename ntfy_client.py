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

import settings as settings_module

log = logging.getLogger("skywatch.ntfy")

DEFAULT_NTFY_BASE = "https://ntfy.sh"
BANNER_DURATION_SECONDS = 10 * 60


def _ntfy_base():
    """Reads the configured server from settings (admin panel), falling
    back to the public ntfy.sh instance if none is set - self-hosted
    instances like ntfy.grandedata.no won't work at all against the
    hardcoded public default."""
    return settings_module.get_settings().get("ntfy_server") or DEFAULT_NTFY_BASE

_lock = threading.Lock()
_banner = {"text": None, "expires_at": 0}
_subscriber_thread = None
_subscriber_topic = None
_subscriber_server = None


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
            f"{_ntfy_base()}/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority},
            timeout=5,
        )
    except Exception as e:
        log.warning("Failed to send ntfy alert: %s", e)


def _subscribe_loop(topic):
    """Long-lived SSE connection to ntfy's topic stream. Reconnects on any
    failure with a short backoff - this must never crash the thread. The
    URL is rebuilt on every reconnect attempt (not just once at thread
    start) so a server change in the admin panel takes effect on the next
    retry rather than requiring a full restart."""
    while True:
        url = f"{_ntfy_base()}/{topic}/sse"
        try:
            # (connect_timeout, read_timeout) - without a read timeout, a
            # connection that stalls without cleanly closing (common after
            # network blips) hangs indefinitely instead of reconnecting,
            # which is what caused the long delay before a message showed
            # up. ntfy sends a keepalive at least every ~45s, so 60s means
            # one missed keepalive triggers a reconnect instead of a
            # silent, unbounded wait.
            with requests.get(url, stream=True, timeout=(5, 60)) as resp:
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
    """(Re)start the background subscriber if the topic or server changed.
    Safe to call repeatedly (e.g. every time admin settings are saved) -
    it only spins up a new thread when something actually changed. A
    server-only change (same topic, different ntfy_server) also restarts
    the current connection immediately rather than waiting for the next
    natural reconnect."""
    global _subscriber_thread, _subscriber_topic, _subscriber_server
    if not topic:
        return
    server = _ntfy_base()
    if (_subscriber_thread and _subscriber_thread.is_alive()
            and _subscriber_topic == topic and _subscriber_server == server):
        return  # already running for this exact topic+server
    _subscriber_topic = topic
    _subscriber_server = server
    _subscriber_thread = threading.Thread(target=_subscribe_loop, args=(topic,), daemon=True)
    _subscriber_thread.start()
    log.info("Started ntfy subscriber for topic '%s' on %s", topic, server)
