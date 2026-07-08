"""Minimal geohash encoder (no external dependency)."""
from __future__ import annotations

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode(lat: float, lng: float, precision: int = 7) -> str:
    lat_lo, lat_hi = -90.0, 90.0
    lng_lo, lng_hi = -180.0, 180.0
    gh: list[str] = []
    bit = 0
    ch = 0
    even = True
    while len(gh) < precision:
        if even:
            mid = (lng_lo + lng_hi) / 2
            if lng > mid:
                ch = (ch << 1) | 1
                lng_lo = mid
            else:
                ch = ch << 1
                lng_hi = mid
        else:
            mid = (lat_lo + lat_hi) / 2
            if lat > mid:
                ch = (ch << 1) | 1
                lat_lo = mid
            else:
                ch = ch << 1
                lat_hi = mid
        even = not even
        bit += 1
        if bit == 5:
            gh.append(_BASE32[ch])
            bit = 0
            ch = 0
    return "".join(gh)
