import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("skywatch")

# ---------------------------------------------------------------------------
# Config (all via environment variables so nothing is hardcoded)
# ---------------------------------------------------------------------------
AIRCRAFT_JSON_URL = os.environ.get("AIRCRAFT_JSON_URL", "http://127.0.0.1/tar1090/data/aircraft.json")
RECEIVER_LAT = float(os.environ.get("RECEIVER_LAT", "0"))  # set your antenna's actual latitude
RECEIVER_LON = float(os.environ.get("RECEIVER_LON", "0"))  # set your antenna's actual longitude
MAX_RANGE_KM = float(os.environ.get("MAX_RANGE_KM", "70"))
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "1"))
STATE_FILE = os.environ.get("STATE_FILE", "/var/lib/skywatch/last_seen.json")
DISTANCE_LOG_FILE = os.environ.get("DISTANCE_LOG_FILE", "/var/lib/skywatch/distance_log.jsonl")
ADSBDB_BASE = os.environ.get("ADSBDB_BASE", "https://api.adsbdb.com/v0")
AIRHEX_APIKEY = os.environ.get("AIRHEX_APIKEY", "")  # optional, blank = free/watermarked tier
ADSBDB_CACHE_TTL = int(os.environ.get("ADSBDB_CACHE_TTL_SECONDS", str(6 * 3600)))
MIN_GROUNDSPEED_FOR_ETA = 30  # knots; below this we don't trust an ETA estimate
LANDED_THRESHOLD_KM = 8  # if remaining distance to destination is under this, call it landed
VALID_CALLSIGN = re.compile(r"^[A-Z0-9]{3,8}$")  # rejects garbage like '@@@@@@@@'
LANDED_ALT_THRESHOLD_FT = 2000  # last known altitude below this = likely just landed, not just out of range
LANDED_DISPLAY_SECONDS = 60  # how long a "LANDET" badge stays up after a plane disappears

app = Flask(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_state = {
    "active": False,
    "aircraft_list": [],  # all currently in-range aircraft, enriched, sorted by distance
    "last": None,          # last known aircraft + timestamp, enriched, survives restarts
}
_callsign_cache = {}  # callsign -> (expiry_ts, adsbdb_response_or_None)
_aircraft_cache = {}  # hex -> (expiry_ts, adsbdb_response_or_None)
_max_distance_by_hex = {}  # hex -> farthest distance_km ever recorded for that aircraft
_prev_active_hexes = set()  # hex set from the previous poll, to detect disappearances
_prev_enriched_by_hex = {}  # hex -> last enriched entry seen while active
_landed_cache = {}  # hex -> {"data": enriched entry with landed=True, "expires_at": epoch}
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


# Known airline groups whose registered_owner sometimes includes a
# subsidiary/country suffix in ADSBdb's data (e.g. "Wizz Air Hungary Zrt",
# "Ryanair DAC", "Malta Air") - normalized down to one universal brand name
# regardless of which national subsidiary actually operates the aircraft.
OWNER_NAME_NORMALIZATION = [
    ("wizz air", "Wizz Air"),
    ("ryanair", "Ryanair"),
    ("malta air", "Ryanair"),
    ("easyjet", "easyJet"),
    ("norwegian", "Norwegian Air Shuttle"),
    ("vueling", "Vueling"),
    ("lufthansa", "Lufthansa"),
    ("klm", "KLM"),
    ("air france", "Air France"),
    ("british airways", "British Airways"),
    ("finnair", "Finnair"),
    ("air baltic", "airBaltic"),
    ("swiss international", "Swiss"),
    ("austrian airlines", "Austrian Airlines"),
    ("eurowings", "Eurowings"),
    ("icelandair", "Icelandair"),
]


def normalize_owner_name(name):
    if not name:
        return name
    lowered = name.lower()
    for keyword, brand in OWNER_NAME_NORMALIZATION:
        if keyword in lowered:
            return brand
    return name


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
    registration = aircraft_info.get("registration") if aircraft_info else None
    aircraft_type = aircraft_info.get("icao_type") if aircraft_info else None
    registered_owner = normalize_owner_name(aircraft_info.get("registered_owner")) if aircraft_info else None
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

    entry = {
        "hex": ac.get("hex"),
        "callsign": callsign or None,
        "flight_iata": with_carrier_prefix(flight_iata_raw, carrier_for_iata),
        "flight_icao": with_carrier_prefix(flight_icao_raw, carrier_for_icao),
        "airline_name": normalize_owner_name(airline.get("name")) if airline else registered_owner,
        "airline_logo": airline_logo_url(logo_source),
        "registration": registration,
        "aircraft_type": aircraft_type,
        "registration_country_iso": registration_country_iso,
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
        "distance_km": round(haversine_km(RECEIVER_LAT, RECEIVER_LON, lat, lon), 1) if lat and lon else None,
        "seen_epoch": now_epoch,
    }

    if lat and lon:
        eta = estimate_eta(lat, lon, gs, destination, now_epoch)
        entry["eta"] = eta

    return entry


def poll_loop():
    load_state_file()
    load_distance_log()
    while True:
        try:
            poll_once()
        except Exception as e:
            log.exception("Poll failed: %s", e)
        time.sleep(POLL_INTERVAL_SECONDS)


def poll_once():
    global _prev_active_hexes, _prev_enriched_by_hex

    r = requests.get(AIRCRAFT_JSON_URL, timeout=4)
    r.raise_for_status()
    data = r.json()
    aircraft_list = data.get("aircraft", [])

    candidates = []
    now = time.time()
    for ac in aircraft_list:
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            continue
        callsign = (ac.get("flight") or "").strip()
        if not VALID_CALLSIGN.match(callsign):
            continue

        raw_alt = ac.get("alt_baro")
        if raw_alt == "ground":
            # Already on the ground the first time we see it (e.g. taxiing
            # after landing) - show it as landed directly, distinct from the
            # disappearance-based inference below. Only set expiry the first
            # time so it doesn't keep re-extending while it sits/taxis.
            hexid = ac.get("hex")
            if hexid and hexid not in _landed_cache:
                landed_entry = enrich(ac)
                landed_entry["altitude_ft"] = 0
                landed_entry["landed"] = True
                _landed_cache[hexid] = {"data": landed_entry, "expires_at": now + LANDED_DISPLAY_SECONDS}
            continue

        alt = raw_alt
        if not isinstance(alt, (int, float)):
            alt = ac.get("alt_geom")  # fall back for aircraft that only send geometric altitude
        if not isinstance(alt, (int, float)):  # still nothing usable - skip
            continue
        dist = haversine_km(RECEIVER_LAT, RECEIVER_LON, lat, lon)

        # Log every aircraft's farthest-seen distance regardless of the
        # display range cutoff below - this is how you discover the
        # antenna's true range even beyond the current MAX_RANGE_KM setting.
        # Cheap (no API calls) since it doesn't go through enrich().
        record_distance({
            "hex": ac.get("hex"),
            "callsign": callsign,
            "flight_iata": None,
            "flight_icao": None,
            "registration": None,
            "distance_km": round(dist, 1),
            "altitude_ft": alt,
        })

        if dist <= MAX_RANGE_KM:
            candidates.append((dist, ac))

    current_hexes = {ac.get("hex") for _, ac in candidates}

    # Any hex that was active last poll but isn't now: if its last known
    # altitude was low, it likely just landed rather than simply going out
    # of range - keep showing it with a "landed" badge for a while.
    for hexid in _prev_active_hexes - current_hexes:
        last = _prev_enriched_by_hex.get(hexid)
        if not last:
            continue
        alt = last.get("altitude_ft")
        if alt is not None and alt <= LANDED_ALT_THRESHOLD_FT:
            landed_entry = dict(last)
            landed_entry["landed"] = True
            _landed_cache[hexid] = {"data": landed_entry, "expires_at": now + LANDED_DISPLAY_SECONDS}

    # Prune expired landed entries, and any that reappeared as active again
    for hexid in list(_landed_cache.keys()):
        if hexid in current_hexes or _landed_cache[hexid]["expires_at"] < now:
            del _landed_cache[hexid]

    with _lock:
        if not candidates and not _landed_cache:
            _state["active"] = False
            _state["aircraft_list"] = []
            _prev_active_hexes = set()
            _prev_enriched_by_hex = {}
            return

        if candidates:
            # Sort by distance to pick the closest as the idle fallback, but
            # display order is by hex (stable) so rotation doesn't reshuffle
            # every poll just because planes' relative distances changed.
            candidates.sort(key=lambda c: c[0])
            closest_enriched = enrich(candidates[0][1])
            display_order = sorted(candidates, key=lambda c: c[1].get("hex", ""))
            enriched_list = [enrich(ac) for _, ac in display_order]
            _state["last"] = closest_enriched
        else:
            enriched_list = []

        landed_list = [entry["data"] for entry in _landed_cache.values()]
        enriched_list = enriched_list + landed_list

        _state["active"] = True
        _state["aircraft_list"] = enriched_list

    _prev_active_hexes = current_hexes
    _prev_enriched_by_hex = {ac["hex"]: ac for ac in enriched_list if not ac.get("landed")} if candidates else {}

    save_state_file()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    with _lock:
        return jsonify({
            "active": _state["active"],
            "aircraft_list": _state["aircraft_list"],
            "last": _state["last"],
            "server_time": datetime.now(timezone.utc).isoformat(),
        })


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
    if RECEIVER_LAT == 0 and RECEIVER_LON == 0:
        log.warning("RECEIVER_LAT/RECEIVER_LON are not set (still 0,0) - "
                    "distance and closest-aircraft selection will be wrong. "
                    "Set them to your antenna's actual coordinates.")
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
