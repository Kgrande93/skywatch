"""
Minimal dict-based i18n - no new dependency (flask-babel etc. would be
overkill for two languages). Language is a single shared setting (admin
panel + both screen templates all read the same value).

Usage in a route:
    lang = get_lang()
    return render_template("index.html", t=get_strings(lang), lang=lang, ...)

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
        "waiting_for_first_aircraft": "Venter på det første flyet \u2026",
        "source_local": "Lokal antenne",
        "source_opensky_own": "OpenSky (egen mottaker)",
        "source_opensky_all": "OpenSky (område)",
        "last_aircraft_seen": "Siste fly sett på himmelen",
        "heading_to": "på vei til",
        "waiting_to_reconnect": "Venter på å koble til mottakeren igjen \u2026",
        "watching_for_next": "Antenne tilkoblet \u2014 venter på neste \u2026",
        "listening_for_signals": "Antenne tilkoblet, lytter etter ADS-B-signaler \u2026",
        "estimated_landing_around": "estimert landing rundt",
        "likely_landed_around": "sannsynligvis landet rundt",
        # admin
        "admin_title": "Skywatch Admin",
        "admin_login_placeholder": "Admin-passord",
        "admin_login_button": "Logg inn",
        "admin_login_error": "Feil passord.",
        "admin_currently_active": "Aktiv nå",
        "admin_data_source": "Datakilde",
        "admin_source_local": "Lokal antenne (readsb/tar1090)",
        "admin_source_opensky_own": "OpenSky — egen mottaker (gratis)",
        "admin_source_opensky_all": "OpenSky — område (bruker kreditter)",
        "admin_opensky_client_id": "OpenSky client ID",
        "admin_opensky_client_secret": "OpenSky client secret",
        "admin_opensky_tier": "OpenSky-kontonivå",
        "admin_tier_anonymous": "Anonym (400 kreditter/dag)",
        "admin_tier_registered": "Registrert (4 000 kreditter/dag)",
        "admin_tier_feeder": "Aktiv feeder (8 000 kreditter/dag)",
        "admin_area": "Område",
        "admin_receiver_position": "Antennens posisjon",
        "admin_receiver_position_note": "Klikk eller dra markøren for å sette hvor antennen din faktisk er. Brukes til avstandsberegning uansett datakilde.",
        "admin_max_range": "Maks rekkevidde (km)",
        "admin_latitude": "Breddegrad (latitude)",
        "admin_longitude": "Lengdegrad (longitude)",
        "admin_local_url": "Lokal aircraft.json-URL",
        "admin_local_url_note": "Kun brukt når datakilden er lokal antenne. Standard: http://127.0.0.1/tar1090/data/aircraft.json",
        "admin_timezone": "Tidssone",
        "admin_timezone_note": "IANA-tidssonenavn, f.eks. Europe/Oslo. Brukes til sesongfunksjoner (snø, julenissen, fyrverkeri) slik at de trigges til riktig lokalt tidspunkt.",
        "admin_max_range_note": "Kun for lokal antenne. Hvor langt unna et fly fortsatt regnes som «i rekkevidde» — kan trygt settes høyt siden det ikke koster noe ekstra. For OpenSky styres rekkevidden av radius-innstillingen under i stedet.",
        "admin_area_irrelevant": "Brukes kun når datakilden er «OpenSky — område». Har ingen effekt for lokal antenne eller din egen OpenSky-mottaker.",
        "admin_radius": "Radius",
        "admin_stat_area": "km² areal",
        "admin_stat_credits": "kreditter/kall",
        "admin_stat_interval": "sek/oppdatering",
        "admin_notifications": "Varsler",
        "admin_ntfy_server": "Ntfy-server (la stå tom for offentlig ntfy.sh)",
        "admin_ntfy_topic": "Ntfy-emne (topic)",
        "admin_ntfy_messages_enabled": "Vis meldinger sendt til dette emnet som banner på skjermen (10 min)",
        "admin_ntfy_emergency_enabled": "Send varsel til dette emnet ved nødsquawk (7500/7600/7700)",
        "admin_display": "Skjerm",
        "admin_brightness": "Lysstyrke (0-100)",
        "admin_brightness_note": "Gjelder kun for fysiske Skywatch Lite-skjermer — har ingen effekt på denne nettsiden.",
        "admin_language": "Språk",
        "admin_save": "Lagre innstillinger",
        "admin_logout": "Logg ut",
        "admin_password_section": "Passord",
        "admin_current_password": "Nåværende passord",
        "admin_new_password": "Nytt passord (min. 8 tegn)",
        "admin_confirm_password": "Bekreft nytt passord",
        "admin_change_password": "Bytt passord",
        "admin_area_warning": (
            "Du har valgt et større område enn anbefalte 25 km radius. "
            "Dette koster flere kreditter per oppdatering, som betyr at "
            "skjermen oppdateres sjeldnere for at den daglige kvoten skal "
            "vare hele døgnet. For de fleste lokale bruksområder dekker "
            "25 km allerede en god radius \u2014 et større område hjelper "
            "hovedsakelig hvis du vil fange opp trafikk lenger unna i "
            "høy høyde."
        ),
        "admin_intro_title": "Velkommen til Skywatch Admin",
        "admin_intro_body": (
            "Her styrer du alt Skywatch trenger: hvilken datakilde som "
            "brukes (lokal antenne eller OpenSky Network), område og "
            "OpenSky-kontonivå, varsler via ntfy, skjerminnstillinger for "
            "en tilkoblet Skywatch Lite-enhet, og admin-passordet ditt. "
            "Endringer lagres og tas i bruk med det samme \u2014 ingen "
            "omstart av tjenesten nødvendig."
        ),
        "admin_intro_dismiss": "Skjønner, sett i gang",
    },
    "en": {
        "antenna_connected_prefix": "Connected",
        "no_antenna_connection": "No connection",
        "no_server_connection": "No server connection",
        "connecting_to_antenna": "Connecting to antenna \u2026",
        "tracking_aircraft": "Tracking {count} aircraft",
        "no_aircraft_nearby": "No aircraft nearby",
        "no_data_yet": "No data yet",
        "waiting_for_first_aircraft": "Waiting for the first aircraft \u2026",
        "source_local": "Local antenna",
        "source_opensky_own": "OpenSky (own receiver)",
        "source_opensky_all": "OpenSky (area)",
        "last_aircraft_seen": "Last aircraft seen in the sky",
        "heading_to": "heading to",
        "waiting_to_reconnect": "Waiting to reconnect to the receiver \u2026",
        "watching_for_next": "Antenna connected \u2014 watching for the next one \u2026",
        "listening_for_signals": "Antenna connected, listening for ADS-B signals \u2026",
        "estimated_landing_around": "estimated landing around",
        "likely_landed_around": "likely landed around",
        "admin_title": "Skywatch Admin",
        "admin_login_placeholder": "Admin password",
        "admin_login_button": "Log in",
        "admin_login_error": "Wrong password.",
        "admin_currently_active": "Currently active",
        "admin_data_source": "Data source",
        "admin_source_local": "Local antenna (readsb/tar1090)",
        "admin_source_opensky_own": "OpenSky — own receiver (free)",
        "admin_source_opensky_all": "OpenSky — area query (uses credits)",
        "admin_opensky_client_id": "OpenSky client ID",
        "admin_opensky_client_secret": "OpenSky client secret",
        "admin_opensky_tier": "OpenSky account tier",
        "admin_tier_anonymous": "Anonymous (400 credits/day)",
        "admin_tier_registered": "Registered (4,000 credits/day)",
        "admin_tier_feeder": "Active feeder (8,000 credits/day)",
        "admin_area": "Area",
        "admin_receiver_position": "Receiver position",
        "admin_receiver_position_note": "Click or drag the marker to set where your antenna actually is. Used for distance calculations regardless of data source.",
        "admin_max_range": "Max range (km)",
        "admin_latitude": "Latitude",
        "admin_longitude": "Longitude",
        "admin_local_url": "Local aircraft.json URL",
        "admin_local_url_note": "Only used when the data source is local antenna. Default: http://127.0.0.1/tar1090/data/aircraft.json",
        "admin_timezone": "Timezone",
        "admin_timezone_note": "IANA timezone name, e.g. Europe/Oslo. Used for seasonal features (snow, Santa, fireworks) so they trigger at the right local moment.",
        "admin_max_range_note": "Local antenna only. How far away an aircraft still counts as \"in range\" — safe to set high since it costs nothing extra. For OpenSky, range is controlled by the radius setting below instead.",
        "admin_area_irrelevant": "Only used when the data source is \"OpenSky — area query\". It has no effect for local antenna or your own OpenSky receiver.",
        "admin_radius": "Radius",
        "admin_stat_area": "km² area",
        "admin_stat_credits": "credits/call",
        "admin_stat_interval": "sec/update",
        "admin_notifications": "Notifications",
        "admin_ntfy_server": "Ntfy server (leave blank for the public ntfy.sh)",
        "admin_ntfy_topic": "Ntfy topic",
        "admin_ntfy_messages_enabled": "Show messages sent to this topic as a screen banner (10 min)",
        "admin_ntfy_emergency_enabled": "Send an alert to this topic on emergency squawk (7500/7600/7700)",
        "admin_display": "Display",
        "admin_brightness": "Brightness (0-100)",
        "admin_brightness_note": "Only applies to physical Skywatch Lite displays — has no effect on this web page.",
        "admin_language": "Language",
        "admin_save": "Save settings",
        "admin_logout": "Log out",
        "admin_password_section": "Password",
        "admin_current_password": "Current password",
        "admin_new_password": "New password (min. 8 characters)",
        "admin_confirm_password": "Confirm new password",
        "admin_change_password": "Change password",
        "admin_area_warning": (
            "You've selected a larger area than the recommended 25 km "
            "radius. This costs more credits per update, which means the "
            "display will refresh less often to make your daily quota "
            "last a full day. For most local flight-spotting use, 25 km "
            "already covers a generous radius \u2014 a bigger area mainly "
            "helps if you want to catch high-altitude traffic passing "
            "further out."
        ),
        "admin_intro_title": "Welcome to Skywatch Admin",
        "admin_intro_body": (
            "This is where you control everything Skywatch needs: which "
            "data source is used (local antenna or OpenSky Network), area "
            "and OpenSky account tier, notifications via ntfy, display "
            "settings for a connected Skywatch Lite device, and your "
            "admin password. Changes save and take effect immediately "
            "\u2014 no service restart needed."
        ),
        "admin_intro_dismiss": "Got it, let's go",
    },
}


def get_lang():
    lang = settings_module.get_settings().get("language", DEFAULT_LANG)
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def get_strings(lang=None):
    return STRINGS[lang if lang in SUPPORTED_LANGS else DEFAULT_LANG]
