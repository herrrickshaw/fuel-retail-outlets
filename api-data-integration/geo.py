"""Shared great-circle helpers for the toll/retail-outlet analysis scripts."""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two (lat, lng) points given in degrees."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def haversine_km_or_inf(lat1, lng1, lat2, lng2) -> float:
    """Like haversine_km but returns inf for unusable input (None, non-numeric)."""
    try:
        return haversine_km(lat1, lng1, lat2, lng2)
    except (TypeError, ValueError):
        return float("inf")


def haversine_km_nonzero_or_inf(lat1, lng1, lat2, lng2) -> float:
    """Like haversine_km but returns inf if any coordinate is falsy (None or 0)."""
    if not all([lat1, lng1, lat2, lng2]):
        return float("inf")
    return haversine_km(lat1, lng1, lat2, lng2)
