"""
Ntfy integration via polling, not a long-lived SSE stream.

SSE turned out to be unreliable against a self-hosted ntfy behind a
reverse proxy - messages arrived in batches only on timeout/reconnect
instead of live, most likely because of response buffering somewhere in
the proxy chain (or requests' own stream handling) that's impractical to
debug/fix remotely with confidence. Polling ntfy's own /json?poll=1
endpoint sidesteps all of that: it's a normal request/response, not a
held-open connection, so nothing in between has a reason to buffer it.

Also used for the automatic emergency-squawk alert (send-side only,
independent of polling).
"""
import logging
import threading
import time

import requests

log = logging.getLogger("skywatch.ntfy")

DEFAULT_NTFY_BASE = "https://ntfy.sh"
BANNER_DURATION_SECONDS = 10 * 60
POLL_INTERVAL_SECONDS = 5

_lock = threading.Lock()
_banner = {"text": None, "expires_at": 0}
_poller_thread = None
_poller_topic = None
_poller_server = None
_stop_event = threading.Event()


def _ntfy_base():
    import settings as settings_module
    return settings_module.get_settings().get("ntfy_server") or DEFAULT_NTFY_BASE


def current_banner():
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


def _poll_loop(topic):
    """Polls for new messages since the last one we've seen. First poll
    uses since=<now> so we don't replay the topic's entire history on
    every restart - only messages published after the poller starts."""
    last_since = str(int(time.time()))
    while not _stop_event.is_set():
        url = f"{_ntfy_base()}/{topic}/json"
        try:
            resp = requests.get(url, params={"poll": "1", "since": last_since}, timeout=10)
            resp.raise_for_status()
            for line in resp.text.strip().splitlines():
                if not line.strip():
                    continue
                try:
                    payload = __import__("json").loads(line)
                except ValueError:
                    continue
                if payload.get("event") != "message":
                    continue
                if payload.get("time"):
                    last_since = str(int(payload["time"]) + 1)
                text = payload.get("message", "")
                if text:
                    _set_banner(text)
        except Exception as e:
            log.warning("ntfy poll failed (will retry): %s", e)
        _stop_event.wait(POLL_INTERVAL_SECONDS)


def start_subscriber(topic):
    """(Re)starts the poller if the topic or server changed. Safe to call
    repeatedly (e.g. every time admin settings are saved)."""
    global _poller_thread, _poller_topic, _poller_server, _stop_event
    if not topic:
        return
    server = _ntfy_base()
    if (_poller_thread and _poller_thread.is_alive()
            and _poller_topic == topic and _poller_server == server):
        return  # already running for this exact topic+server

    if _poller_thread and _poller_thread.is_alive():
        _stop_event.set()
        _poller_thread.join(timeout=POLL_INTERVAL_SECONDS + 2)

    _stop_event = threading.Event()
    _poller_topic = topic
    _poller_server = server
    _poller_thread = threading.Thread(target=_poll_loop, args=(topic,), daemon=True)
    _poller_thread.start()
    log.info("Started ntfy poller for topic '%s' on %s (every %ds)", topic, server, POLL_INTERVAL_SECONDS)
