"""
Minimal dict-based i18n - no new dependency (flask-babel etc. would be
overkill for two languages). Language is picked via a cookie, default
Norwegian, switchable from a small link on every page.

Usage in a route:
    lang = get_lang()
    return render_template("index.html", t=STRINGS[lang], lang=lang, ...)

Usage in a template:
    {{ t.antenna_connected }}

Usage in JS (inject once near the top of the template):
    const T = {{ t | tojson }};
    ... T.antenna_connected ...
"""
import settings as settings_module

DEFAULT_LANG = "no"
SUPPORTED_LANGS = ("no", "en")

STRINGS = {
    "no": {
        # status / connection
        "antenna_connected_prefix": "Tilkoblet",
        "no_antenna_connection": "Ingen tilkobling",
        "no_server_connection": "Ingen serverforbindelse",
        "connecting_to_antenna": "Kobler til antenne \u2026",
        "tracking_aircraft": "Sporer {count} fly",
        "no_aircraft_nearby": "Ingen fly i nærheten",
        "no_data_yet": "Venter på data",
        "waiting_for_first_aircraft": "Venter på det første flyet",
        "source_local": "Lokal antenne",
        "source_opensky_own": "OpenSky (egen mottaker)",
        "source_opensky_all": "OpenSky (område)",
        # admin
        "admin_title": "Skywatch Admin",
        "admin_login_placeholder": "Admin-passord",
        "admin_login_button": "Logg inn",
        "admin_login_error": "Feil passord.",
        "admin_currently_active": "Aktiv nå",
        "admin_data_source": "Datakilde",
        "admin_area": "Område",
        "admin_notifications": "Varsler",
        "admin_display": "Skjerm",
        "admin_save": "Lagre innstillinger",
        "admin_logout": "Logg ut",
        "admin_area_warning": (
            "Du har valgt et større område enn anbefalte 25 km radius. "
            "Dette koster flere kreditter per oppdatering, som betyr at "
            "skjermen oppdateres sjeldnere for at den daglige kvoten skal "
            "vare hele døgnet. For de fleste lokale bruksområder dekker "
            "25 km allerede en god radius \u2014 et større område hjelper "
            "hovedsakelig hvis du vil fange opp trafikk lenger unna i "
            "høy høyde."
        ),
    },
    "en": {
        "antenna_connected_prefix": "Connected",
        "no_antenna_connection": "No connection",
        "no_server_connection": "No server connection",
        "connecting_to_antenna": "Connecting to antenna \u2026",
        "tracking_aircraft": "Tracking {count} aircraft",
        "no_aircraft_nearby": "No aircraft nearby",
        "no_data_yet": "No data yet",
        "waiting_for_first_aircraft": "Waiting for the first aircraft",
        "source_local": "Local antenna",
        "source_opensky_own": "OpenSky (own receiver)",
        "source_opensky_all": "OpenSky (area)",
        "admin_title": "Skywatch Admin",
        "admin_login_placeholder": "Admin password",
        "admin_login_button": "Log in",
        "admin_login_error": "Wrong password.",
        "admin_currently_active": "Currently active",
        "admin_data_source": "Data source",
        "admin_area": "Area",
        "admin_notifications": "Notifications",
        "admin_display": "Display",
        "admin_save": "Save settings",
        "admin_logout": "Log out",
        "admin_area_warning": (
            "You've selected a larger area than the recommended 25 km "
            "radius. This costs more credits per update, which means the "
            "display will refresh less often to make your daily quota "
            "last a full day. For most local flight-spotting use, 25 km "
            "already covers a generous radius \u2014 a bigger area mainly "
            "helps if you want to catch high-altitude traffic passing "
            "further out."
        ),
    },
}


def get_lang():
    """Language is a single shared setting (admin panel + both screen
    templates all read the same value) rather than a per-visitor cookie -
    a wall-mounted display has no one to individually prefer a language."""
    lang = settings_module.get_settings().get("language", DEFAULT_LANG)
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def get_strings(lang=None):
    return STRINGS[lang if lang in SUPPORTED_LANGS else DEFAULT_LANG]
