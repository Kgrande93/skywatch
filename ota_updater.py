"""
Self-update via `git pull` for the Skywatch desktop app (not to be
confused with Skywatch Lite's ESP32 device OTA - that's a separate
mechanism entirely). Runs as a background thread, either on a nightly
schedule (default 03:00 local time) or triggered manually from the
admin panel's "Check for updates now" button.

Since the app runs as an unprivileged systemd user with no permission to
call `systemctl restart` on itself, a successful update re-execs the
current process in place via os.execv() - this reloads every Python
module fresh, picking up the pulled changes, without needing any
elevated privileges.
"""
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

import settings as settings_module

log = logging.getLogger("skywatch.ota")

REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def _run(cmd, timeout=60):
    return subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=timeout)


def check_and_apply(manual=False):
    """Runs one update check/apply cycle. Returns a status dict describing
    what happened - used both by the nightly scheduler and the admin
    panel's manual button."""
    result = {"checked_at": time.time(), "manual": manual, "status": "error", "message": "", "commit": None}

    try:
        before = _run(["git", "rev-parse", "HEAD"])
        if before.returncode != 0:
            result["message"] = "Not a git repository, or git isn't available"
            _save_result(result)
            return result
        before_hash = before.stdout.strip()

        fetch = _run(["git", "fetch", "--quiet"])
        if fetch.returncode != 0:
            result["message"] = f"git fetch failed: {fetch.stderr.strip()[:200]}"
            _save_result(result)
            return result

        # --ff-only fails safely (no auto-merge, no conflicts) if the
        # local checkout has diverged - that needs a human to look at it
        # rather than risk an automatic merge on a running server.
        pull = _run(["git", "pull", "--ff-only", "--quiet"])
        if pull.returncode != 0:
            result["message"] = f"git pull failed (diverged or local changes?): {pull.stderr.strip()[:200]}"
            _save_result(result)
            return result

        after = _run(["git", "rev-parse", "HEAD"])
        after_hash = after.stdout.strip()
        result["commit"] = after_hash[:8]

        if before_hash == after_hash:
            result["status"] = "up_to_date"
            result["message"] = "Already up to date"
            _save_result(result)
            return result

        # New commits pulled - install any dependency changes before
        # restarting, so new code doesn't crash on a missing import.
        pip = _run(["venv/bin/pip", "install", "-r", "requirements.txt", "--quiet"])
        if pip.returncode != 0:
            result["status"] = "error"
            result["message"] = f"Pulled new code but pip install failed: {pip.stderr.strip()[:200]}"
            _save_result(result)
            return result

        result["status"] = "updated"
        result["message"] = f"Updated {before_hash[:8]} -> {after_hash[:8]}, restarting"
        _save_result(result)
        log.info("Update applied (%s -> %s), restarting process", before_hash[:8], after_hash[:8])

        # Give the settings write (and any in-flight request) a moment,
        # then re-exec in place - reloads all modules fresh with the new
        # code, no systemd/root privileges required.
        threading.Timer(2.0, _restart).start()
        return result

    except Exception as e:
        result["message"] = f"Unexpected error: {e}"
        _save_result(result)
        log.exception("Update check failed")
        return result


def _restart():
    os.execv(sys.executable, [sys.executable] + sys.argv)


def _save_result(result):
    settings_module.update_settings({
        "last_update_check": result["checked_at"],
        "last_update_status": result["status"],
        "last_update_message": result["message"],
        "last_update_commit": result["commit"],
    })


def _scheduler_loop():
    """Runs once/day at the configured hour (default 03:00 local time).
    Sleeps in short chunks so a toggle change or manual trigger elsewhere
    isn't stuck behind a near-24h wait, and re-reads settings on each
    wake so a disabled toggle actually takes effect."""
    while True:
        now = datetime.now()
        target_hour = int(settings_module.get_settings().get("auto_update_hour", 3))
        next_run = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        sleep_seconds = (next_run - now).total_seconds()

        slept = 0
        while slept < sleep_seconds:
            time.sleep(min(300, sleep_seconds - slept))
            slept += 300

        if settings_module.get_settings().get("auto_update_enabled", False):
            log.info("Running scheduled nightly update check")
            check_and_apply(manual=False)


def start_scheduler():
    threading.Thread(target=_scheduler_loop, daemon=True).start()
