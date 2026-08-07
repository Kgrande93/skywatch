"""
Admin panel blueprint for Skywatch.

Self-contained authentication - no dependency on external auth providers
(Authelia, OIDC, etc.), since this needs to work for anyone who downloads
and runs Skywatch on their own, not just Kai's own homelab.

Login: single admin password, hashed (never stored/compared in plaintext).
Set it once via the ADMIN_PASSWORD_HASH env var - generate the hash with:

    python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('yourpassword'))"
"""
import os
import time
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import settings as settings_module

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")

# Simple in-memory rate limit on login attempts, keyed by IP. Not shared
# across multiple app instances/workers, but stops naive brute-forcing.
_login_attempts = {}  # ip -> list of epoch timestamps of recent failed attempts
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300


def _rate_limited(ip):
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def _record_failed_attempt(ip):
    _login_attempts.setdefault(ip, []).append(time.time())


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if not ADMIN_PASSWORD_HASH:
        return "ADMIN_PASSWORD_HASH is not set - admin panel is disabled until it is configured.", 503

    error = None
    if request.method == "POST":
        ip = request.remote_addr
        if _rate_limited(ip):
            error = "Too many attempts - wait a few minutes and try again."
        else:
            submitted = request.form.get("password", "")
            if check_password_hash(ADMIN_PASSWORD_HASH, submitted):
                session["admin_authenticated"] = True
                session.permanent = True
                return redirect(url_for("admin.dashboard"))
            _record_failed_attempt(ip)
            error = "Wrong password."
    return render_template("admin_login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/", methods=["GET"])
@login_required
def dashboard():
    s = settings_module.get_settings()
    if s.get("area_center_lat") is None:
        s["area_center_lat"] = float(os.environ.get("RECEIVER_LAT", "0"))
    if s.get("area_center_lon") is None:
        s["area_center_lon"] = float(os.environ.get("RECEIVER_LON", "0"))
    return render_template("admin_dashboard.html", settings=s)


@admin_bp.route("/settings", methods=["POST"])
@login_required
def save_settings():
    form = request.form
    changes = {
        "data_source": form.get("data_source", "local"),
        "opensky_client_id": form.get("opensky_client_id", "").strip(),
        "ntfy_topic": form.get("ntfy_topic", "").strip(),
        "ntfy_messages_enabled": form.get("ntfy_messages_enabled") == "on",
        "ntfy_emergency_squawk_enabled": form.get("ntfy_emergency_squawk_enabled") == "on",
        "brightness": int(form.get("brightness", 80)),
    }
    # Only overwrite the secret if a new one was actually typed - the
    # dashboard shows a masked placeholder, not the real value, so an
    # untouched field must not blank out the stored secret.
    new_secret = form.get("opensky_client_secret", "").strip()
    if new_secret:
        changes["opensky_client_secret"] = new_secret

    for key in ("area_center_lat", "area_center_lon", "area_radius_km"):
        val = form.get(key, "").strip()
        changes[key] = float(val) if val else None

    settings_module.update_settings(changes)
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/settings/credit-estimate", methods=["POST"])
@login_required
def credit_estimate():
    """Live radius -> bbox -> credit cost -> poll interval calculator,
    called via fetch() from the dashboard's map as the user drags the
    radius slider."""
    import opensky_client as osc
    import geo

    data = request.get_json(force=True)
    center_lat, center_lon = data.get("center_lat"), data.get("center_lon")
    radius_km = data.get("radius_km")
    tier = data.get("tier", "registered")

    if None in (center_lat, center_lon, radius_km):
        return jsonify({"error": "incomplete area"}), 400

    result = geo.estimate(center_lat, center_lon, radius_km)
    interval = osc.recommended_poll_interval_seconds(tier, credits_per_call=result["credits_per_call"])
    result["recommended_interval_seconds"] = interval
    return jsonify(result)
