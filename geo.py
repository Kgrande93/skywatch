"""
Small geo helper: converts a center point + radius (km) into the
lat/lon bounding box OpenSky's /states/all expects, and estimates the
resulting credit cost per call. Kept separate from opensky_client.py
since this is pure math with no network calls.
"""
import math

# OpenSky credit table for /states/all, by bounding-box area in square
# degrees of lat/lon (from their docs).
CREDIT_TIERS = [
    (25, 1),
    (100, 2),
    (400, 3),
    (float("inf"), 4),
]

RECOMMENDED_MAX_RADIUS_KM = 25  # only used as the *default* slider position - never
                                # for the warning threshold, since that must track the
                                # real credit-cost boundary, which varies by latitude
                                # (see credits_for_area) and has nothing to do with 25


def radius_to_bbox(center_lat, center_lon, radius_km):
    """Returns (lamin, lomin, lamax, lomax). Longitude degrees shrink with
    latitude (great-circle distance per degree of longitude = 111km * cos(lat)),
    so the box is wider than tall in degrees except at the equator."""
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(math.cos(math.radians(center_lat)), 0.01))
    return (
        center_lat - lat_delta,
        center_lon - lon_delta,
        center_lat + lat_delta,
        center_lon + lon_delta,
    )


def bbox_area_sq_deg(lamin, lomin, lamax, lomax):
    return abs(lamax - lamin) * abs(lomax - lomin)


def credits_for_area(area_sq_deg):
    for threshold, credits in CREDIT_TIERS:
        if area_sq_deg <= threshold:
            return credits
    return CREDIT_TIERS[-1][1]


def estimate(center_lat, center_lon, radius_km):
    import math
    lamin, lomin, lamax, lomax = radius_to_bbox(center_lat, center_lon, radius_km)
    area = bbox_area_sq_deg(lamin, lomin, lamax, lomax)
    credits = credits_for_area(area)
    # Real-world circular area (what the radius actually selects) in km2 -
    # far more intuitive to show a Norwegian user than "square degrees",
    # which is only meaningful for the OpenSky credit-cost lookup itself.
    area_km2 = round(math.pi * radius_km ** 2)
    return {
        "bbox": {"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax},
        "area_sq_deg": round(area, 2),
        "area_km2": area_km2,
        "credits_per_call": credits,
        "over_recommended": credits > 1,  # warn only once it actually costs more,
                                            # not at an arbitrary km value unrelated
                                            # to the real (latitude-dependent) threshold
    }
