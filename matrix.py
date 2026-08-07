"""
Builds the /api/matrix response consumed by Skywatch Lite (and the
emulator) - the one JSON contract between the backend and the physical
display. Kept separate from app.py's own /api/status shape since the
matrix has very different constraints (tiny screen, fixed field budget)
from the web frontend.
"""
import ntfy_client

# Maps a simplified logo key the firmware knows how to draw. Extend this
# as more airlines get a hand-drawn logo in firmware - anything not in
# here just falls back to a plain colored circle using logo_color.
AIRLINE_LOGO_KEYS = {
    "UA": "united",
    "HA": "hawaiian",
    "WN": "southwest",
}

# Rough per-airline brand colors for the fallback plain-circle logo.
AIRLINE_COLORS = {
    "SK": "#1f4fbf",  # SAS
    "WF": "#e2231a",  # Widerøe
    "DY": "#003087",  # Norwegian
}
DEFAULT_LOGO_COLOR = "#3a4652"


def _logo_fields(airline_iata):
    if not airline_iata:
        return {"logo": "default", "logo_color": DEFAULT_LOGO_COLOR}
    key = AIRLINE_LOGO_KEYS.get(airline_iata.upper())
    if key:
        return {"logo": key, "logo_color": None}
    return {"logo": "default", "logo_color": AIRLINE_COLORS.get(airline_iata.upper(), DEFAULT_LOGO_COLOR)}


def build_matrix_response(state, antenna_connected):
    """state is the same dict app.py already maintains (_state), so this
    reads the same data the web frontend does - no separate poll needed."""
    banner_text, banner_expires_at = ntfy_client.current_banner()

    response = {
        "antenna": "#3ddc84" if antenna_connected else "#ff4d4d",
        "server": "#3ddc84",
        "banner_text": banner_text,
        "banner_expires_at": banner_expires_at,
    }

    aircraft = state.get("last")
    if not aircraft or not state.get("active"):
        response.update({
            "mode": "idle",
            "name": "SKYWATCH",
            "line4": "NO AIRCRAFT",
            "line5": "IN RANGE",
            "progress": 0,
        })
        return response

    if aircraft.get("emergency"):
        response.update({
            "mode": "flight",
            "name": aircraft.get("callsign") or "----",
            "route": _route_text(aircraft),
            "actype": aircraft.get("aircraft_type") or "",
            "line4": f"EMERGENCY {aircraft.get('squawk', '')}".strip(),
            "line5": "SQUAWK ACTIVE",
            "accent": "#ff4d4d",
            "progress": _progress(aircraft),
        })
        response.update(_logo_fields(_airline_iata(aircraft)))
        return response

    if aircraft.get("landed"):
        response.update({
            "mode": "flight",
            "name": aircraft.get("callsign") or "----",
            "route": _route_text(aircraft),
            "actype": aircraft.get("aircraft_type") or "",
            "line4": "LANDED",
            "line5": "",
            "accent": "#3ddc84",
            "progress": 1.0,
        })
        response.update(_logo_fields(_airline_iata(aircraft)))
        return response

    response.update({
        "mode": "flight",
        "name": aircraft.get("callsign") or "----",
        "route": _route_text(aircraft),
        "actype": aircraft.get("aircraft_type") or "",
        "line4": f"ALT {_fmt_alt(aircraft.get('altitude_ft'))}  SPD {_fmt_spd(aircraft.get('groundspeed_kt'))}",
        "line5": f"DIST {aircraft.get('distance_km', '?')}KM",
        "accent": "#c7ced4",
        "progress": _progress(aircraft),
    })
    response.update(_logo_fields(_airline_iata(aircraft)))
    return response


def _airline_iata(aircraft):
    flight_iata = aircraft.get("flight_iata") or ""
    return flight_iata[:2] if len(flight_iata) >= 2 else None


def _route_text(aircraft):
    origin = (aircraft.get("origin") or {}).get("iata_code")
    dest = (aircraft.get("destination") or {}).get("iata_code")
    if origin and dest:
        return f"{origin}-{dest}"
    return ""


def _fmt_alt(ft):
    if ft is None:
        return "?"
    return f"{ft/1000:.1f}K" if ft >= 1000 else str(int(ft))


def _fmt_spd(kt):
    if kt is None:
        return "?"
    return f"{int(kt)}KT"


def _progress(aircraft):
    eta = aircraft.get("eta")
    if not eta or eta.get("landed_estimate"):
        return 1.0
    return 0.5  # no reliable "percent of route flown" without origin dep time - placeholder
