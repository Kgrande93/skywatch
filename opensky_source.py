"""
Adapts OpenSky state vectors into the same shape as a local readsb
aircraft.json entry, so poll_once() and enrich() in app.py don't need to
know or care which source the data came from - only the fetch step at the
top of poll_once() branches on data_source.

OpenSky state vector field order (index):
0 icao24, 1 callsign, 2 origin_country, 3 time_position, 4 last_contact,
5 longitude, 6 latitude, 7 baro_altitude(m), 8 on_ground, 9 velocity(m/s),
10 true_track, 11 vertical_rate(m/s), 12 sensors, 13 geo_altitude(m),
14 squawk, 15 spi, 16 position_source, 17 category (only with extended=1)
"""
import settings as settings_module
import opensky_client as osc
import geo

_client = None


def _get_client():
    global _client
    s = settings_module.get_settings()
    if _client is None:
        _client = osc.OpenSkyClient(
            client_id=s.get("opensky_client_id") or None,
            client_secret=s.get("opensky_client_secret") or None,
        )
    else:
        # credentials may have changed via the admin panel since the
        # client was created - keep it in sync rather than restarting
        _client.client_id = s.get("opensky_client_id") or None
        _client.client_secret = s.get("opensky_client_secret") or None
    return _client


def _m_to_ft(m):
    return m * 3.28084 if m is not None else None


def _ms_to_kt(ms):
    return ms * 1.94384 if ms is not None else None


def _ms_to_fpm(ms):
    return ms * 196.85 if ms is not None else None


def _state_to_ac_dict(state):
    (icao24, callsign, origin_country, time_position, last_contact,
     lon, lat, baro_alt_m, on_ground, velocity_ms, true_track,
     vertical_rate_ms, sensors, geo_alt_m, squawk, spi, position_source,
     *rest) = state + [None] * (18 - len(state))

    category = rest[0] if rest else None

    return {
        "hex": icao24,
        "flight": (callsign or "").strip() if callsign else "",
        "lat": lat,
        "lon": lon,
        "alt_baro": "ground" if on_ground else _m_to_ft(baro_alt_m),
        "alt_geom": _m_to_ft(geo_alt_m),
        "gs": _ms_to_kt(velocity_ms),
        "baro_rate": _ms_to_fpm(vertical_rate_ms),
        "category": _opensky_category_to_readsb(category),
        "squawk": squawk,
        "emergency": "general" if squawk in ("7500", "7600", "7700") else None,
        "dbFlags": 0,  # OpenSky doesn't provide this - military detection unavailable via this source
        "r": None,     # OpenSky states don't include registration/type - ADSBdb lookup in enrich() covers this
        "t": None,
    }


# OpenSky's numeric category codes map roughly onto readsb's letter
# categories - only the ones that matter for existing filtering logic
# (NON_AIRCRAFT_CATEGORIES, CATEGORY_LABELS in app.py) are mapped here.
_OPENSKY_CATEGORY_MAP = {
    None: None, 0: None,
    1: "A1", 2: "A1", 3: "A2", 4: "A3", 5: "A5", 6: "A4", 7: "A7",
    9: "B1", 10: "B2", 11: "B3", 12: "B4", 13: "B5", 14: "B6", 15: "B7",
    16: "C1", 17: "C2", 18: "C2", 19: "C3", 20: "C3",
}


def _opensky_category_to_readsb(cat):
    return _OPENSKY_CATEGORY_MAP.get(cat)


def fetch_aircraft_dict():
    """Returns {"aircraft": [...]} in the same shape poll_once() already
    expects from AIRCRAFT_JSON_URL - drop-in replacement for that fetch."""
    s = settings_module.get_settings()
    client = _get_client()

    if s["data_source"] == "opensky_own":
        result = client.states_own()
    else:  # "opensky_all" - area query, costs credits
        lat = s.get("area_center_lat")
        lon = s.get("area_center_lon")
        radius_km = s.get("area_radius_km") or 25
        if lat is None or lon is None:
            raise RuntimeError("area_center_lat/lon not set - configure the area in the admin panel first")
        bbox = geo.radius_to_bbox(lat, lon, radius_km)
        result = client.states_all(lamin=bbox[0], lomin=bbox[1], lamax=bbox[2], lomax=bbox[3])

    states = result.get("states") or []
    return {"aircraft": [_state_to_ac_dict(s) for s in states]}
