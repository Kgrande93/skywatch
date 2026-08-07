import json
import logging
import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, render_template, request, redirect, url_for

import santa_route
import settings as settings_module
import ntfy_client
import matrix
import i18n
import opensky_client
from admin import admin_bp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("skywatch")

# ---------------------------------------------------------------------------
# Config (all via environment variables so nothing is hardcoded)
# ---------------------------------------------------------------------------
AIRCRAFT_JSON_URL = os.environ.get("AIRCRAFT_JSON_URL", "http://127.0.0.1/tar1090/data/aircraft.json")


def get_receiver_location():
    """Receiver position now lives in the admin panel (settings.json),
    since it's also the center point for the OpenSky area query - not a
    separate env var anymore. Falls back to RECEIVER_LAT/RECEIVER_LON env
    vars once, on first run, so existing deployments keep working until
    someone opens the admin panel and re-saves the area."""
    s = settings_module.get_settings()
    lat = s.get("area_center_lat")
    lon = s.get("area_center_lon")
    if lat is not None and lon is not None:
        return lat, lon
    return (
        float(os.environ.get("RECEIVER_LAT", "0")),
        float(os.environ.get("RECEIVER_LON", "0")),
    )
MAX_RANGE_KM = float(os.environ.get("MAX_RANGE_KM", "70"))
REGION_TEXT = os.environ.get("REGION_TEXT", "Gardermoen area")
# ANTENNA_LOCATION_TEXT retired - no longer meaningful now that the data
# source (and therefore what "location" even means) is chosen per-instance
# in the admin panel rather than being a fixed physical antenna.
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Oslo")
TZ = ZoneInfo(TIMEZONE)
SANTA_CRUISE_ALTITUDE_FT = 241200  # deliberately absurd - well past the Karman line
SANTA_CLIMB_DESCEND_FRACTION = 0.15  # first/last 15% of each leg is climb/descent
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "1"))
STATE_FILE = os.environ.get("STATE_FILE", "/var/lib/skywatch/last_seen.json")
DISTANCE_LOG_FILE = os.environ.get("DISTANCE_LOG_FILE", "/var/lib/skywatch/distance_log.jsonl")
ADSBDB_BASE = os.environ.get("ADSBDB_BASE", "https://api.adsbdb.com/v0")
AIRHEX_APIKEY = os.environ.get("AIRHEX_APIKEY", "")  # optional, blank = free/watermarked tier
ADSBDB_CACHE_TTL = int(os.environ.get("ADSBDB_CACHE_TTL_SECONDS", str(6 * 3600)))
MIN_GROUNDSPEED_FOR_ETA = 30  # knots; below this we don't trust an ETA estimate
LANDED_THRESHOLD_KM = 8  # if remaining distance to destination is under this, call it landed
VALID_CALLSIGN = re.compile(r"^[A-Z0-9]{3,8}$")  # rejects garbage like '@@@@@@@@'
NON_FLIGHT_CALLSIGNS = {"00000000"}  # ground vehicles etc. often broadcast this placeholder
# ADS-B emitter categories C1-C5 are surface vehicles and fixed obstacles,
# not aircraft (DO-260B spec) - never show these as "planes in the sky".
NON_AIRCRAFT_CATEGORIES = {"C1", "C2", "C3", "C4", "C5"}

app = Flask(__name__)
app.secret_key = settings_module.get_or_create_secret_key()
app.register_blueprint(admin_bp)

_settings = settings_module.get_settings()
if _settings.get("ntfy_topic"):
    ntfy_client.start_subscriber(_settings["ntfy_topic"])

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_state = {
    "active": False,
    "aircraft_list": [],  # all currently in-range aircraft, enriched, sorted by distance
    "last": None,          # last known aircraft + timestamp, enriched, survives restarts
    "last_poll_success_epoch": None,  # last time we successfully fetched aircraft.json
}
ANTENNA_TIMEOUT_SECONDS = int(os.environ.get("ANTENNA_TIMEOUT_SECONDS", "20"))
_callsign_cache = {}  # callsign -> (expiry_ts, adsbdb_response_or_None)
_aircraft_cache = {}  # hex -> (expiry_ts, adsbdb_response_or_None)
_max_distance_by_hex = {}  # hex -> farthest distance_km ever recorded for that aircraft
_ground_since = {}  # hex -> epoch when this aircraft was first seen with ground status
_emergency_alerted = set()  # hex codes we've already sent an ntfy alert for

EMERGENCY_SQUAWKS = {"7500": "HIJACK", "7600": "RADIO FAILURE", "7700": "GENERAL EMERGENCY"}


def check_emergency_squawk(entry):
    """Fires an ntfy alert the first time a given aircraft (by hex) is seen
    squawking an emergency code - not on every poll while it stays active,
    and resets once the squawk clears so a later, separate emergency from
    the same aircraft still alerts."""
    hexid = entry.get("hex")
    squawk = entry.get("squawk")
    settings = settings_module.get_settings()

    if squawk in EMERGENCY_SQUAWKS:
        if hexid and hexid not in _emergency_alerted:
            _emergency_alerted.add(hexid)
            if settings.get("ntfy_emergency_squawk_enabled") and settings.get("ntfy_topic"):
                label = EMERGENCY_SQUAWKS[squawk]
                callsign = entry.get("callsign") or hexid
                ntfy_client.send_message(
                    settings["ntfy_topic"],
                    title=f"Emergency squawk {squawk}",
                    message=f"{callsign} is squawking {squawk} ({label})",
                )
    elif hexid in _emergency_alerted:
        _emergency_alerted.discard(hexid)
AIRCRAFT_CACHE_TTL = int(os.environ.get("AIRCRAFT_CACHE_TTL_SECONDS", str(30 * 24 * 3600)))  # registration barely changes


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_state_file():
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            with _lock:
                _state["last"] = data
            log.info("Loaded last-seen state from %s", STATE_FILE)
    except FileNotFoundError:
        log.info("No existing state file at %s, starting fresh", STATE_FILE)
    except Exception as e:
        log.warning("Could not load state file: %s", e)


def save_state_file():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(_state["last"], f)
    except Exception as e:
        log.warning("Could not save state file: %s", e)


def load_distance_log():
    """Rebuild the max-distance-per-aircraft table from the log file on
    disk, so records survive restarts."""
    try:
        with open(DISTANCE_LOG_FILE, "r") as f:
            count = 0
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                hexid, dist = rec.get("hex"), rec.get("distance_km")
                if hexid and dist is not None:
                    if hexid not in _max_distance_by_hex or dist > _max_distance_by_hex[hexid]:
                        _max_distance_by_hex[hexid] = dist
                    count += 1
        log.info("Loaded distance log: %d records, %d distinct aircraft", count, len(_max_distance_by_hex))
    except FileNotFoundError:
        log.info("No existing distance log at %s, starting fresh", DISTANCE_LOG_FILE)
    except Exception as e:
        log.warning("Could not load distance log: %s", e)


def record_distance(enriched):
    """Append a line to the distance log only when this aircraft (by hex)
    has set a new farthest-seen distance record."""
    hexid = enriched.get("hex")
    dist = enriched.get("distance_km")
    if not hexid or dist is None:
        return
    prev = _max_distance_by_hex.get(hexid)
    if prev is not None and dist <= prev:
        return
    _max_distance_by_hex[hexid] = dist
    rec = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hex": hexid,
        "callsign": enriched.get("callsign"),
        "flight": enriched.get("flight_iata") or enriched.get("flight_icao"),
        "registration": enriched.get("registration"),
        "distance_km": dist,
        "altitude_ft": enriched.get("altitude_ft"),
    }
    try:
        os.makedirs(os.path.dirname(DISTANCE_LOG_FILE), exist_ok=True)
        with open(DISTANCE_LOG_FILE, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        log.warning("Could not write distance log: %s", e)


def lookup_callsign(callsign):
    """Look up flight route + airline via ADSBdb, with a simple TTL cache."""
    callsign = callsign.strip()
    now = time.time()
    cached = _callsign_cache.get(callsign)
    if cached and cached[0] > now:
        return cached[1]

    result = None
    try:
        r = requests.get(f"{ADSBDB_BASE}/callsign/{callsign}", timeout=4)
        if r.status_code == 200:
            result = r.json().get("response", {}).get("flightroute")
    except Exception as e:
        log.warning("ADSBdb lookup failed for %s: %s", callsign, e)

    _callsign_cache[callsign] = (now + ADSBDB_CACHE_TTL, result)
    return result


def lookup_aircraft(hex_code):
    """Look up registration/type via ADSBdb, with a long-lived cache since
    an aircraft's registration essentially never changes."""
    if not hex_code:
        return None
    now = time.time()
    cached = _aircraft_cache.get(hex_code)
    if cached and cached[0] > now:
        return cached[1]

    result = None
    try:
        r = requests.get(f"{ADSBDB_BASE}/aircraft/{hex_code}", timeout=4)
        if r.status_code == 200:
            result = r.json().get("response", {}).get("aircraft")
    except Exception as e:
        log.warning("ADSBdb aircraft lookup failed for %s: %s", hex_code, e)

    _aircraft_cache[hex_code] = (now + AIRCRAFT_CACHE_TTL, result)
    return result


# ADS-B emitter category -> a plain-language label. Only used as a fallback
# in the UI when there's no known airline name to show instead - a category
# label next to a real airline name would just be redundant clutter.
CATEGORY_LABELS = {
    "A1": "Private aircraft",
    "A2": "Commercial",
    "A3": "Commercial",
    "A4": "Commercial",
    "A5": "Commercial",
    "A6": "Commercial",
    "A7": "Helicopter",
}
# These categories are worth showing even when we already know the
# operator/owner name (e.g. "Helicopter" next to "Oslo Police District") -
# unlike "Commercial", which is just redundant noise next to a real airline
# name and should only appear as a fallback when nothing else is known.
CATEGORY_ALWAYS_SHOW = {"A1", "A7"}

# ICAO operator codes for fractional-ownership / on-demand private jet
# charter operators. ADSBdb returns a real operator name for these (e.g.
# "NetJets"), so the normal category-label fallback never fires - but
# they aren't scheduled commercial airlines, and that distinction should
# still show up on screen. Add more codes here as needed.
PRIVATE_CHARTER_OPERATOR_CODES = {
    "EJA",  # NetJets Aviation (US)
    "NJE",  # NetJets Europe
    "VJT",  # VistaJet (Malta)
    "LXJ",  # Flexjet (US)
    "FLJ",  # Flexjet Operations UK
}

# ICAO operator codes mapped to a known company name - used ONLY when
# ADSBdb/the aircraft lookup returns no name at all for that flight.
# Never overrides a name that was actually returned, even if it looks
# generic or inconsistent - this is strictly a last-resort fallback.
FALLBACK_OPERATOR_NAMES = {
    "WIF": "Widerøe Flyveselskap",
    "NAX": "Norwegian Air Shuttle",
    "WZZ": "Wizz Air Hungary",
    "WAB": "Wizz Air Malta",
    "WUK": "Wizz Air UK",
    "WAZ": "Wizz Air Abu Dhabi",
    "OCN": "Discover Airlines",
    "EJA": "NetJets",
    "NJE": "NetJets Europe",
    "VJT": "VistaJet",
    "LXJ": "Flexjet",
    "FLJ": "Flexjet",
}


def airline_logo_url(airline):
    if not airline:
        return None
    code = airline.get("iata") or airline.get("icao")
    if not code:
        return None
    if AIRHEX_APIKEY:
        import hashlib
        raw = f"{code}_200_80_r_{AIRHEX_APIKEY}"
        md5 = hashlib.md5(raw.encode()).hexdigest()
        return f"https://content.airhex.com/content/logos/airlines_{code}_200_80_r.png?md5apikey={md5}"
    # Unauthenticated demo tier - works but may carry a small watermark.
    return f"https://content.airhex.com/content/logos/airlines_{code}_200_80_r.png"


def estimate_eta(last_lat, last_lon, groundspeed_kt, destination, seen_at_epoch):
    """Rough ETA based on last known position/speed and great-circle distance
    to the scheduled destination airport. This is an estimate, not a real
    schedule - actual approach path and speed will differ."""
    if not destination or groundspeed_kt is None or groundspeed_kt < MIN_GROUNDSPEED_FOR_ETA:
        return None
    remaining_km = haversine_km(last_lat, last_lon, destination["latitude"], destination["longitude"])
    if remaining_km <= LANDED_THRESHOLD_KM:
        return {"epoch": seen_at_epoch, "landed_estimate": True}
    speed_kmh = groundspeed_kt * 1.852
    eta_epoch = seen_at_epoch + (remaining_km / speed_kmh) * 3600
    return {"epoch": eta_epoch, "landed_estimate": False}


def enrich(ac):
    """Build the enriched aircraft dict shown to the frontend from a raw
    aircraft.json entry plus ADSBdb + logo lookups."""
    callsign = (ac.get("flight") or "").strip()
    lat, lon = ac.get("lat"), ac.get("lon")
    alt_ft = ac.get("alt_baro") if isinstance(ac.get("alt_baro"), (int, float)) else ac.get("alt_geom")
    gs = ac.get("gs")
    vrate = ac.get("baro_rate") if isinstance(ac.get("baro_rate"), (int, float)) else ac.get("geom_rate")
    now_epoch = time.time()

    route = lookup_callsign(callsign) if callsign else None
    airline = route.get("airline") if route else None
    destination = route.get("destination") if route else None
    origin = route.get("origin") if route else None

    aircraft_info = lookup_aircraft(ac.get("hex"))
    # readsb's own db-file (r/t fields, when --db-file is configured) is a
    # more complete source for registration/type than ADSBdb - prefer it,
    # falling back to ADSBdb only when readsb doesn't have it.
    registration = ac.get("r") or (aircraft_info.get("registration") if aircraft_info else None)
    aircraft_type = ac.get("t") or (aircraft_info.get("icao_type") if aircraft_info else None)
    registered_owner = aircraft_info.get("registered_owner") if aircraft_info else None
    owner_country = aircraft_info.get("registered_owner_country_name") if aircraft_info else None
    registration_country_iso = aircraft_info.get("registered_owner_country_iso_name") if aircraft_info else None

    flight_iata_raw = route.get("callsign_iata") if route else None
    flight_icao_raw = route.get("callsign_icao") if route else None
    airline_iata = airline.get("iata") if airline else None
    airline_icao = airline.get("icao") if airline else None

    def with_carrier_prefix(code, carrier):
        if not code:
            return None
        if code[0].isalpha():  # already has a carrier letter prefix
            return code
        if carrier:
            return f"{carrier}{code}"
        return None  # can't safely prefix it - let the frontend fall back to the raw callsign

    # Fall back to the other code if one is missing (some airlines only
    # have one of iata/icao populated in ADSBdb's data).
    carrier_for_iata = airline_iata or airline_icao
    carrier_for_icao = airline_icao or airline_iata

    # If there's no route/airline match (e.g. military or an operator not
    # in the flightroute database), the aircraft lookup's operator flag
    # code (e.g. "WZZ" for Wizz Air) can still get us a logo.
    logo_source = airline
    if not logo_source and aircraft_info:
        flag_code = aircraft_info.get("registered_owner_operator_flag_code")
        if flag_code:
            logo_source = {"icao": flag_code, "iata": None}

    operator_flag_code = aircraft_info.get("registered_owner_operator_flag_code") if aircraft_info else None
    best_operator_code = airline_icao or operator_flag_code

    # Two different quality levels get conflated if treated the same:
    # - route_airline_name comes from the flightroute lookup and is always
    #   a real, full company name when present - never touched.
    # - registered_owner comes from the aircraft registry and can be a
    #   bare/inconsistent string (e.g. "Wideroe") - so a known-operator
    #   fallback name is preferred over it, and it's only used as the
    #   final resort when nothing else is available.
    route_airline_name = airline.get("name") if airline else None
    fallback_name = FALLBACK_OPERATOR_NAMES.get(best_operator_code.upper()) if best_operator_code else None
    display_name = route_airline_name or fallback_name or registered_owner
    if not display_name:
        # No name from any source - logged so real gaps in
        # FALLBACK_OPERATOR_NAMES can be found from actual traffic
        # instead of guessed at.
        log.info("No airline name for callsign=%s operator_code=%s hex=%s",
                  callsign, best_operator_code, ac.get("hex"))

    is_private_charter = bool(best_operator_code) and best_operator_code.upper() in PRIVATE_CHARTER_OPERATOR_CODES
    if is_private_charter:
        category_label = "Private charter"
        category_always_show = True
    else:
        category_label = CATEGORY_LABELS.get(ac.get("category"))
        category_always_show = ac.get("category") in CATEGORY_ALWAYS_SHOW

    entry = {
        "hex": ac.get("hex"),
        "callsign": callsign or None,
        "flight_iata": with_carrier_prefix(flight_iata_raw, carrier_for_iata),
        "flight_icao": with_carrier_prefix(flight_icao_raw, carrier_for_icao),
        "airline_name": display_name,
        "airline_logo": airline_logo_url(logo_source),
        "registration": registration,
        "aircraft_type": aircraft_type,
        "registration_country_iso": registration_country_iso,
        "category_label": category_label,
        "category_always_show": category_always_show,
        "is_military": bool(ac.get("dbFlags", 0) & 1),
        "operator_country": owner_country if not airline else None,
        "origin": origin,
        "destination": destination,
        "altitude_ft": alt_ft,
        "vertical_rate_fpm": vrate,
        "groundspeed_kt": gs,
        "squawk": ac.get("squawk"),
        "emergency": ac.get("emergency") if ac.get("emergency") not in (None, "none") else None,
        "lat": lat,
        "lon": lon,
        "distance_km": round(haversine_km(*get_receiver_location(), lat, lon), 1) if lat and lon else None,
        "seen_epoch": now_epoch,
    }

    if lat and lon:
        eta = estimate_eta(lat, lon, gs, destination, now_epoch)
        entry["eta"] = eta

    return entry


def get_poll_interval_seconds():
    """For a local antenna, the fixed env-configured interval (usually 1s)
    is fine - no quota to worry about. For OpenSky, the interval must be
    derived from the account tier and selected area so the daily credit
    budget actually lasts the full day, instead of a fixed interval that
    has no relationship to the quota (which is what caused the 400-credit
    anonymous tier to exhaust itself in minutes)."""
    s = settings_module.get_settings()
    source = s.get("data_source", "local")
    if source == "local":
        return POLL_INTERVAL_SECONDS
    if source == "opensky_own":
        return 10  # free/unlimited endpoint - no quota math needed, just a sane refresh rate
    # opensky_all - actually costs credits, compute from area + tier
    import geo
    import opensky_client as osc
    lat, lon = s.get("area_center_lat"), s.get("area_center_lon")
    radius_km = s.get("area_radius_km") or 25
    if lat is None or lon is None:
        # Area not configured yet - use the most conservative interval
        # (anonymous tier, worst-case 4-credit area) rather than
        # POLL_INTERVAL_SECONDS, which is a local-antenna value with no
        # relationship to OpenSky's quota at all.
        return osc.recommended_poll_interval_seconds("anonymous", credits_per_call=4)
    result = geo.estimate(lat, lon, radius_km)
    return osc.recommended_poll_interval_seconds(s.get("opensky_tier", "registered"),
                                                  credits_per_call=result["credits_per_call"])


def poll_loop():
    load_state_file()
    load_distance_log()
    while True:
        sleep_seconds = get_poll_interval_seconds()
        try:
            poll_once()
        except opensky_client.OpenSkyRateLimitError as e:
            # Hit the quota despite the interval math (e.g. area/tier changed
            # mid-day after credits were already spent this cycle) - back off
            # for what OpenSky actually tells us to wait, capped at 1 hour so
            # a huge retry_after can't accidentally freeze the app for a day.
            wait = min(e.retry_after or 3600, 3600)
            log.warning("OpenSky rate limit hit, backing off for %ds", wait)
            _interruptible_sleep(wait)
            continue
        except Exception as e:
            log.exception("Poll failed: %s", e)
        _interruptible_sleep(sleep_seconds)


def _interruptible_sleep(seconds):
    """Like time.sleep(), but wakes immediately if settings change via the
    admin panel - so switching data source, area, or tier takes effect on
    the very next poll instead of waiting out whatever sleep (possibly up
    to an hour, during a rate-limit backoff) happened to already be in
    progress. wait() returns True if the event fired, False on a normal
    timeout - either way we clear it and let the loop re-read settings."""
    woken = settings_module.poll_wake_event.wait(timeout=seconds)
    if woken:
        settings_module.poll_wake_event.clear()
        log.info("Settings changed - waking poll loop early")


def poll_once():
    source = settings_module.get_settings().get("data_source", "local")
    if source in ("opensky_own", "opensky_all"):
        import opensky_source
        data = opensky_source.fetch_aircraft_dict()
    else:
        r = requests.get(AIRCRAFT_JSON_URL, timeout=4)
        r.raise_for_status()
        data = r.json()
    aircraft_list = data.get("aircraft", [])
    now = time.time()

    with _lock:
        _state["last_poll_success_epoch"] = now

    candidates = []
    ground_hexes_now = set()
    for ac in aircraft_list:
        if ac.get("category") in NON_AIRCRAFT_CATEGORIES:
            continue

        lat, lon = ac.get("lat"), ac.get("lon")
        callsign = (ac.get("flight") or "").strip()
        hexid = ac.get("hex")

        if (ac.get("alt_baro") == "ground" and hexid and callsign
                and VALID_CALLSIGN.match(callsign) and callsign not in NON_FLIGHT_CALLSIGNS):
            ground_hexes_now.add(hexid)
            if hexid not in _ground_since:
                _ground_since[hexid] = now
            continue

        if lat is None or lon is None:
            continue
        if not VALID_CALLSIGN.match(callsign) or callsign in NON_FLIGHT_CALLSIGNS:
            continue

        alt = ac.get("alt_baro")
        if not isinstance(alt, (int, float)):
            alt = ac.get("alt_geom")  # fall back for aircraft that only send geometric altitude
        if not isinstance(alt, (int, float)):  # still nothing usable - skip
            continue
        receiver_lat, receiver_lon = get_receiver_location()
        dist = haversine_km(receiver_lat, receiver_lon, lat, lon)

        # Log every aircraft's farthest-seen distance regardless of the
        # display range cutoff below - this is how you discover the
        # antenna's true range even beyond the current MAX_RANGE_KM setting.
        # Cheap (no API calls) since it doesn't go through enrich().
        record_distance({
            "hex": hexid,
            "callsign": callsign,
            "flight_iata": None,
            "flight_icao": None,
            "registration": None,
            "distance_km": round(dist, 1),
            "altitude_ft": alt,
        })

        if dist <= MAX_RANGE_KM:
            candidates.append((dist, ac))

    # Drop tracking for any hex no longer showing ground status - it
    # disappears from the display immediately, no lingering timer.
    for hexid in list(_ground_since.keys()):
        if hexid not in ground_hexes_now:
            del _ground_since[hexid]

    ground_aircraft = [ac for ac in aircraft_list
                       if ac.get("hex") in ground_hexes_now]

    with _lock:
        if not candidates and not ground_aircraft:
            _state["active"] = False
            _state["aircraft_list"] = []
            return

        enriched_list = []
        closest_enriched = None
        if candidates:
            # Sort by distance to pick the closest as the idle fallback, but
            # display order is by hex (stable) so rotation doesn't reshuffle
            # every poll just because planes' relative distances changed.
            candidates.sort(key=lambda c: c[0])
            closest_enriched = enrich(candidates[0][1])
            display_order = sorted(candidates, key=lambda c: c[1].get("hex", ""))
            enriched_list = [enrich(ac) for _, ac in display_order]

        for ac in sorted(ground_aircraft, key=lambda a: a.get("hex", "")):
            entry = enrich(ac)
            entry["landed"] = True
            entry["landed_at_epoch"] = _ground_since.get(ac.get("hex"), now)
            enriched_list.append(entry)

        _state["active"] = True
        _state["aircraft_list"] = enriched_list
        if closest_enriched:
            _state["last"] = closest_enriched

    for entry in enriched_list:
        check_emergency_squawk(entry)

    save_state_file()


# ---------------------------------------------------------------------------
# Holiday effects (snow, fireworks, Santa's sleigh) - all computed live from
# TIMEZONE, no persistent state needed since they're pure functions of "now".
# ---------------------------------------------------------------------------

def first_advent_sunday(year):
    """1st Sunday of Advent = 4th Sunday before Christmas Day."""
    dec25 = date(year, 12, 25)
    days_since_sunday = (dec25.weekday() + 1) % 7  # Mon=0..Sun=6 -> days since last Sunday
    fourth_advent = dec25 - timedelta(days=days_since_sunday)
    return fourth_advent - timedelta(weeks=3)


def get_holiday_flags(now_local):
    year = now_local.year
    today = now_local.date()
    advent1 = first_advent_sunday(year)
    dec30 = date(year, 12, 30)
    show_snow = advent1 <= today <= dec30

    show_fireworks = (
        now_local.month == 1 and now_local.day == 1
        and now_local.hour == 0 and now_local.minute < 5
    )
    return show_snow, show_fireworks


def build_santa_schedule(year):
    """Convert each stop's local arrival time to a UTC epoch, sort
    chronologically, and bookend the list with virtual North Pole stops."""
    schedule = []
    for stop in santa_route.STOPS:
        try:
            tz = ZoneInfo(stop["timezone"])
            local_dt = datetime(year, 12, stop["day"], stop["hour"], stop["minute"], tzinfo=tz)
            schedule.append({"country": stop["country"], "lat": stop["lat"], "lon": stop["lon"],
                              "epoch": local_dt.astimezone(timezone.utc).timestamp()})
        except Exception as e:
            log.warning("Skipping bad Santa stop %s: %s", stop.get("country"), e)

    schedule.sort(key=lambda s: s["epoch"])
    if not schedule:
        return []

    lead = 3600  # 1 hour buffer at each end for the North Pole legs
    north_pole_start = {"country": "the North Pole", "lat": 90.0, "lon": 0.0,
                         "epoch": schedule[0]["epoch"] - lead}
    north_pole_end = {"country": "the North Pole", "lat": 90.0, "lon": 0.0,
                       "epoch": schedule[-1]["epoch"] + lead}
    return [north_pole_start] + schedule + [north_pole_end]


def get_santa_status(now_utc_epoch):
    """Returns a synthetic 'aircraft' entry for Santa if now falls within his
    route window, else None. Checks both this year's and (in early January)
    last year's schedule, since the route can span into Jan 1 briefly."""
    for year in (datetime.fromtimestamp(now_utc_epoch, tz=timezone.utc).year,
                 datetime.fromtimestamp(now_utc_epoch, tz=timezone.utc).year - 1):
        schedule = build_santa_schedule(year)
        if not schedule:
            continue
        if not (schedule[0]["epoch"] <= now_utc_epoch <= schedule[-1]["epoch"]):
            continue

        # Find which leg we're on
        for i in range(len(schedule) - 1):
            leg_start, leg_end = schedule[i], schedule[i + 1]
            if leg_start["epoch"] <= now_utc_epoch <= leg_end["epoch"]:
                duration = leg_end["epoch"] - leg_start["epoch"]
                progress = 0.5 if duration <= 0 else (now_utc_epoch - leg_start["epoch"]) / duration

                distance_km = haversine_km(leg_start["lat"], leg_start["lon"], leg_end["lat"], leg_end["lon"])
                duration_hr = duration / 3600
                groundspeed_kt = (distance_km / 1.852) / duration_hr if duration_hr > 0 else 0
                remaining_km = distance_km * (1 - progress)

                if progress < SANTA_CLIMB_DESCEND_FRACTION:
                    climb_progress = progress / SANTA_CLIMB_DESCEND_FRACTION
                    altitude_ft = SANTA_CRUISE_ALTITUDE_FT * climb_progress
                    vertical_rate = 5000
                elif progress > 1 - SANTA_CLIMB_DESCEND_FRACTION:
                    descend_progress = (1 - progress) / SANTA_CLIMB_DESCEND_FRACTION
                    altitude_ft = SANTA_CRUISE_ALTITUDE_FT * descend_progress
                    vertical_rate = -5000
                else:
                    altitude_ft = SANTA_CRUISE_ALTITUDE_FT
                    vertical_rate = 0

                return {
                    "hex": "santa01",
                    "callsign": "SANTA01",
                    "flight_iata": "SANTA01",
                    "flight_icao": "SANTA01",
                    "is_santa": True,
                    "airline_name": "Santa Airlines",
                    "airline_logo": None,
                    "registration": "SANTA01",
                    "aircraft_type": "Sleigh",
                    "registration_country_iso": None,
                    "category_label": None,
                    "category_always_show": False,
                    "is_military": False,
                    "operator_country": None,
                    "origin": {"iata_code": None, "municipality": leg_start["country"], "name": leg_start["country"], "country_name": None},
                    "destination": {"iata_code": None, "municipality": leg_end["country"], "name": leg_end["country"], "country_name": None},
                    "altitude_ft": round(altitude_ft),
                    "vertical_rate_fpm": vertical_rate,
                    "groundspeed_kt": round(groundspeed_kt),
                    "distance_km": round(remaining_km, 1),
                    "squawk": "XMAS",
                    "emergency": None,
                    "eta": None,
                    "seen_epoch": now_utc_epoch,
                }
    return None


@app.route("/")
def index():
    lang = i18n.get_lang()
    return render_template("index.html", region_text=REGION_TEXT,
                            t=i18n.get_strings(lang), lang=lang)


@app.route("/kiosk")
def kiosk():
    lang = i18n.get_lang()
    return render_template("kiosk.html", region_text=REGION_TEXT,
                            t=i18n.get_strings(lang), lang=lang)





@app.route("/api/status")
def api_status():
    with _lock:
        last_poll = _state["last_poll_success_epoch"]
        antenna_connected = last_poll is not None and (time.time() - last_poll) < ANTENNA_TIMEOUT_SECONDS

        now_utc_epoch = time.time()
        now_local = datetime.now(TZ)
        show_snow, show_fireworks = get_holiday_flags(now_local)
        santa = get_santa_status(now_utc_epoch)

        if santa:
            # Santa joins the rotation alongside whatever real aircraft are
            # currently in range - he doesn't replace normal tracking.
            aircraft_list = [santa] + _state["aircraft_list"]
            response = {
                "active": True,
                "aircraft_list": aircraft_list,
                "last": _state["last"],
            }
        else:
            response = {
                "active": _state["active"],
                "aircraft_list": _state["aircraft_list"],
                "last": _state["last"],
            }

        response["antenna_connected"] = antenna_connected
        response["data_source"] = settings_module.get_settings().get("data_source", "local")
        response["show_snow"] = show_snow
        response["show_fireworks"] = show_fireworks
        response["server_time"] = datetime.now(timezone.utc).isoformat()
        return jsonify(response)


@app.route("/api/matrix")
def api_matrix():
    with _lock:
        last_poll = _state["last_poll_success_epoch"]
        antenna_connected = last_poll is not None and (time.time() - last_poll) < ANTENNA_TIMEOUT_SECONDS
        return jsonify(matrix.build_matrix_response(_state, antenna_connected))


@app.route("/api/range-log")
def api_range_log():
    """Every aircraft's farthest recorded distance, sorted farthest first -
    use this to figure out your antenna's real range and tune MAX_RANGE_KM."""
    records = []
    try:
        with open(DISTANCE_LOG_FILE, "r") as f:
            latest_by_hex = {}
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("hex"):
                    latest_by_hex[rec["hex"]] = rec  # last line per hex = farthest (only written on new records)
            records = sorted(latest_by_hex.values(), key=lambda r: r.get("distance_km", 0), reverse=True)
    except FileNotFoundError:
        pass
    return jsonify(records)


if __name__ == "__main__":
    _startup_lat, _startup_lon = get_receiver_location()
    if _startup_lat == 0 and _startup_lon == 0:
        log.warning("Receiver location is not set (still 0,0) - configure it in the admin panel, "
                    "distance and closest-aircraft selection will be wrong. "
                    "Set them to your antenna's actual coordinates.")
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
