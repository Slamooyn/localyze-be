"""PostGIS query helpers (all I/O lives here; scoring.py stays pure)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

_POINT = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"


def point_in_region(db: Session, lat: float, lng: float) -> dict | None:
    """Resolve a point to its subdistrict (fallback: district). Returns
    {id, name, level} or None if outside coverage."""
    for level in ("subdistrict", "district"):
        row = db.execute(
            text(
                "SELECT id, name, level FROM regions "
                "WHERE level = :level "
                "AND ST_Contains(boundary, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)) "
                "LIMIT 1"
            ),
            {"level": level, "lng": lng, "lat": lat},
        ).mappings().first()
        if row:
            return dict(row)
    return None


def get_demographics(db: Session, region_id: int) -> dict | None:
    row = db.execute(
        text(
            "SELECT region_id, population, density_per_km2, age_distribution, "
            "purchasing_power_index, is_modeled, data_year, source "
            "FROM demographics WHERE region_id = :rid"
        ),
        {"rid": region_id},
    ).mappings().first()
    return dict(row) if row else None


def competitors_in_radius(
    db: Session, lat: float, lng: float, category_id: int, radius_m: int
) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT p.id, p.name, b.name AS brand,
                   COALESCE(b.is_chain, false) AS is_chain, p.rating,
                   ST_Y(p.location::geometry) AS lat, ST_X(p.location::geometry) AS lng,
                   ST_Distance(p.location, {_POINT}) AS distance_m
            FROM places p
            LEFT JOIN brands b ON b.id = p.brand_id
            WHERE p.place_type = 'competitor' AND p.category_id = :cat AND p.is_active
              AND ST_DWithin(p.location, {_POINT}, :radius)
            ORDER BY distance_m
            """
        ),
        {"lng": lng, "lat": lat, "cat": category_id, "radius": radius_m},
    ).mappings().all()
    return [dict(r) for r in rows]


def anchors_in_radius(
    db: Session, lat: float, lng: float, radius_m: int
) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT p.id, p.name, p.anchor_type,
                   ST_Y(p.location::geometry) AS lat, ST_X(p.location::geometry) AS lng,
                   ST_Distance(p.location, {_POINT}) AS distance_m
            FROM places p
            WHERE p.place_type = 'anchor' AND p.is_active
              AND ST_DWithin(p.location, {_POINT}, :radius)
            ORDER BY distance_m
            """
        ),
        {"lng": lng, "lat": lat, "radius": radius_m},
    ).mappings().all()
    return [dict(r) for r in rows]


def nearest_competitor_distance(
    db: Session, lat: float, lng: float, category_id: int
) -> float | None:
    row = db.execute(
        text(
            f"""
            SELECT ST_Distance(p.location, {_POINT}) AS d
            FROM places p
            WHERE p.place_type = 'competitor' AND p.category_id = :cat AND p.is_active
            ORDER BY p.location <-> {_POINT}
            LIMIT 1
            """
        ),
        {"lng": lng, "lat": lat, "cat": category_id},
    ).first()
    return float(row[0]) if row else None


def user_outlets_within(
    db: Session, lat: float, lng: float, radius_m: float, user_id: str
) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT o.id, o.name,
                   ST_Distance(o.location, {_POINT}) AS distance_m
            FROM user_outlets o
            WHERE o.user_id = :uid AND ST_DWithin(o.location, {_POINT}, :radius)
            ORDER BY distance_m
            """
        ),
        {"lng": lng, "lat": lat, "radius": radius_m, "uid": str(user_id)},
    ).mappings().all()
    return [dict(r) for r in rows]
