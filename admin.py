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

import secrets
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import settings as settings_module
import i18n

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ADMIN_PASSWORD_HASH_ENV = os.environ.get("ADMIN_PASSWORD_HASH", "")


def current_password_hash():
    """settings.json overrides the env var once a password change has been
    saved through the panel - env var remains the bootstrap/fallback value
    for first run and for recovering if settings.json is ever wiped."""
    stored = settings_module.get_settings().get("admin_password_hash")
    return stored or ADMIN_PASSWORD_HASH_ENV

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
        # Re-check that a password actually exists on every request, not
        # just whether the session says "authenticated" - otherwise an
        # old session cookie stays valid forever even after the password
        # is cleared/reset, which defeats the point of being able to
        # reset it at all.
        if not current_password_hash():
            session.pop("admin_authenticated", None)
            return redirect(url_for("admin.setup"))
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """First-run flow: if no password is configured anywhere (env or
    settings.json), let the user set one directly in the browser instead
    of having to generate a werkzeug hash in a terminal. Once a password
    exists (either way), this route redirects to the normal login."""
    if current_password_hash():
        return redirect(url_for("admin.login"))

    lang = i18n.get_lang()
    t = i18n.get_strings(lang)
    error = None
    if request.method == "POST":
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if len(new_pw) < 8:
            error = t["admin_setup_error_length"]
        elif new_pw != confirm:
            error = t["admin_setup_error_match"]
        else:
            new_key = secrets.token_hex(32)
            settings_module.update_settings({
                "admin_password_hash": generate_password_hash(new_pw),
                "flask_secret_key": new_key,
            })
            current_app.secret_key = new_key
            session["admin_authenticated"] = True
            session.permanent = True
            return redirect(url_for("admin.dashboard"))
    return render_template("admin_setup.html", error=error, t=t, lang=lang)


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    password_hash = current_password_hash()
    if not password_hash:
        return redirect(url_for("admin.setup"))

    lang = i18n.get_lang()
    t = i18n.get_strings(lang)
    error = None
    if request.method == "POST":
        ip = request.remote_addr
        if _rate_limited(ip):
            error = "Too many attempts - wait a few minutes and try again."
        else:
            submitted = request.form.get("password", "")
            if check_password_hash(password_hash, submitted):
                session["admin_authenticated"] = True
                session.permanent = True
                return redirect(url_for("admin.dashboard"))
            _record_failed_attempt(ip)
            error = t["admin_login_error"]
    return render_template("admin_login.html", error=error, t=t, lang=lang)


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
    lang = i18n.get_lang()
    return render_template("admin_dashboard.html", settings=s, t=i18n.get_strings(lang), lang=lang,
                            supported_langs=i18n.SUPPORTED_LANGS,
                            show_intro=not s.get("admin_intro_seen"))


@admin_bp.route("/dismiss-intro", methods=["POST"])
@login_required
def dismiss_intro():
    settings_module.update_settings({"admin_intro_seen": True})
    return ("", 204)


@admin_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    if not check_password_hash(current_password_hash(), current):
        return render_template("admin_dashboard.html", settings=settings_module.get_settings(),
                                t=i18n.get_strings(i18n.get_lang()), lang=i18n.get_lang(),
                                supported_langs=i18n.SUPPORTED_LANGS,
                                password_error="Current password is incorrect.")
    if len(new_pw) < 8:
        return render_template("admin_dashboard.html", settings=settings_module.get_settings(),
                                t=i18n.get_strings(i18n.get_lang()), lang=i18n.get_lang(),
                                supported_langs=i18n.SUPPORTED_LANGS,
                                password_error="New password must be at least 8 characters.")
    if new_pw != confirm:
        return render_template("admin_dashboard.html", settings=settings_module.get_settings(),
                                t=i18n.get_strings(i18n.get_lang()), lang=i18n.get_lang(),
                                supported_langs=i18n.SUPPORTED_LANGS,
                                password_error="New password and confirmation don't match.")

    new_key = secrets.token_hex(32)
    settings_module.update_settings({
        "admin_password_hash": generate_password_hash(new_pw),
        "flask_secret_key": new_key,
    })
    # Rotating the key invalidates every existing session (including this
    # one) since old cookies are signed with the old key - re-establish
    # this browser's session under the new key so the redirect below
    # doesn't immediately bounce back to login.
    current_app.secret_key = new_key
    session["admin_authenticated"] = True
    session.permanent = True
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/settings", methods=["POST"])
@login_required
def save_settings():
    form = request.form
    changes = {
        "data_source": form.get("data_source", "local"),
        "opensky_client_id": form.get("opensky_client_id", "").strip(),
        "opensky_tier": form.get("opensky_tier", "registered"),
        "ntfy_topic": form.get("ntfy_topic", "").strip(),
        "ntfy_server": form.get("ntfy_server", "").strip().rstrip("/"),
        "ntfy_messages_enabled": form.get("ntfy_messages_enabled") == "on",
        "ntfy_emergency_squawk_enabled": form.get("ntfy_emergency_squawk_enabled") == "on",
        "brightness": int(form.get("brightness", 80)),
        "language": form.get("language", "no"),
        "aircraft_json_url": form.get("aircraft_json_url", "").strip() or None,
        "timezone": form.get("timezone", "").strip() or None,
        "port": int(form["port"]) if form.get("port", "").strip() else None,
        "state_file": form.get("state_file", "").strip() or None,
    }
    # Only overwrite the secret if a new one was actually typed - the
    # dashboard shows a masked placeholder, not the real value, so an
    # untouched field must not blank out the stored secret.
    new_secret = form.get("opensky_client_secret", "").strip()
    if new_secret:
        changes["opensky_client_secret"] = new_secret

    for key in ("area_center_lat", "area_center_lon", "area_radius_km", "max_range_km"):
        val = form.get(key, "").strip()
        changes[key] = float(val) if val else None

    settings_module.update_settings(changes)
    if changes["ntfy_topic"]:
        import ntfy_client
        ntfy_client.start_subscriber(changes["ntfy_topic"])
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
