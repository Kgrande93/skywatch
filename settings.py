"""
Central settings store for Skywatch admin-configurable options.

Unlike the env-var config in app.py (set once at deploy time), these are
meant to be changed at runtime via the /admin panel - so they live in a
small JSON file instead, with env vars only as first-run defaults.
"""
import json
import os
import secrets
import threading

SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "/var/lib/skywatch/settings.json")

_lock = threading.Lock()

# Signaled whenever settings change, so poll_loop() (which may be sleeping
# for up to an hour during a rate-limit backoff, or tens of seconds for a
# normal OpenSky interval) wakes up immediately and re-reads the new
# settings instead of finishing out a stale sleep first. Without this, a
# data-source switch in the admin panel silently does nothing until
# whatever sleep happened to be in progress finishes on its own.
poll_wake_event = threading.Event()

DEFAULTS = {
    "data_source": "local",  # "local" | "opensky_own" | "opensky_all"
    "opensky_client_id": "",
    "opensky_client_secret": "",
    "opensky_tier": "registered",  # "anonymous" | "registered" | "feeder"
    "area_center_lat": None,   # defaults to RECEIVER_LAT env var on first run
    "area_center_lon": None,   # defaults to RECEIVER_LON env var on first run
    "area_radius_km": 25,      # recommended default
    "max_range_km": None,      # falls back to MAX_RANGE_KM env var (default 70) when None
    "aircraft_json_url": None, # falls back to AIRCRAFT_JSON_URL env var when None
    "timezone": None,          # falls back to TIMEZONE env var (default Europe/Oslo) when None
    "port": None,              # falls back to PORT env var (default 5000) when None - requires a restart to take effect
    "state_file": None,        # falls back to STATE_FILE env var when None - requires a restart to take effect
    "auto_update_enabled": False,
    "auto_update_hour": 3,      # 0-23, local time, when the nightly check runs
    "last_update_check": None,
    "last_update_status": None,   # "up_to_date" | "updated" | "error"
    "last_update_message": None,
    "last_update_commit": None,
    "update_available": False,
    "available_commit": None,
    "ntfy_topic": "",
    "ntfy_server": "",  # e.g. https://ntfy.grandedata.no - falls back to https://ntfy.sh when empty
    "ntfy_messages_enabled": False,
    "ntfy_emergency_squawk_enabled": False,
    "brightness": 80,
    "language": "no",  # "no" | "en" - shared by both the screen displays and this admin panel
    "admin_password_hash": None,  # set via the panel's change-password form; falls back to ADMIN_PASSWORD_HASH env var when None
    "admin_intro_seen": False,
}


def _read_raw():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def get_settings():
    with _lock:
        data = dict(DEFAULTS)
        data.update(_read_raw())
        return data


def update_settings(changes: dict):
    with _lock:
        data = dict(DEFAULTS)
        data.update(_read_raw())
        data.update(changes)
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    poll_wake_event.set()  # outside the lock - nothing here needs it held
    return data


def get_or_create_secret_key():
    """Flask session signing key - generated once, persisted alongside
    settings so it survives restarts (a fresh key on every restart would
    invalidate all admin sessions)."""
    data = _read_raw()
    if "flask_secret_key" in data:
        return data["flask_secret_key"]
    key = secrets.token_hex(32)
    update_settings({"flask_secret_key": key})
    return key
