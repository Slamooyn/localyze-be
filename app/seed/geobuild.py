"""Deterministic geometry helpers for the seed (no external deps beyond math)."""
from __future__ import annotations

import math

EARTH_R = 6371000.0  # meters


def haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def rect_multipolygon(w: float, s: float, e: float, n: float) -> str:
    ring = f"{w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}"
    return f"MULTIPOLYGON((({ring})))"


def point_wkt(lng: float, lat: float) -> str:
    return f"POINT({lng} {lat})"


def cell_area_km2(w: float, s: float, e: float, n: float) -> float:
    mid_lat = (s + n) / 2
    width_km = haversine_m(w, mid_lat, e, mid_lat) / 1000
    height_km = haversine_m((w + e) / 2, s, (w + e) / 2, n) / 1000
    return width_km * height_km
