"""Toll-plaza coordinates for the toll<->outlet distance scripts.

The scripts used to place every plaza at a hard-coded state centroid plus jitter re-seeded with
hash(state) before each draw, so all plazas of a state landed on the SAME point (and Python's
salted str hash moved that point between runs); unknown states went to (23, 79). Distances from
those points are meaningless. Now a plaza is only used when its own latitude/longitude are known
(e.g. from NHAI TIS or geocoding); plazas without coordinates are skipped, never invented.
"""
import math


def plaza_lat_lng(row):
    """Return (lat, lng) from a plaza row's latitude/longitude (or lat/lng) columns, else None."""
    for la, lo in (("latitude", "longitude"), ("lat", "lng"), ("lat", "lon")):
        try:
            lat, lng = float(row.get(la)), float(row.get(lo))
        except (TypeError, ValueError):
            continue
        if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    return None
