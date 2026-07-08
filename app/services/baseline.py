"""Percentile baselines, computed once from the static snapshot and cached.

Demographic baselines come straight from the demographics table. Competition and
anchor baselines are sampled by running the raw metrics over a coarse grid across
the pilot city (scoring-algorithm.md §2) — the distribution is static because the
data is a snapshot, so we compute it once at startup.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import geo, scoring

SAMPLE_NX = 18
SAMPLE_NY = 18


@dataclass
class CatBaseline:
    pressure: list[float] = field(default_factory=list)
    per_capita: list[float] = field(default_factory=list)
    nearest: list[float] = field(default_factory=list)
    anchor_raw: list[float] = field(default_factory=list)


@dataclass
class Baselines:
    density: list[float] = field(default_factory=list)
    pp: list[float] = field(default_factory=list)
    per_category: dict[int, CatBaseline] = field(default_factory=dict)


_store: Baselines | None = None


def _city_bbox(db: Session) -> tuple[float, float, float, float]:
    row = db.execute(
        text(
            "SELECT ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g) FROM "
            "(SELECT boundary::geometry g FROM regions WHERE level='city' LIMIT 1) t"
        )
    ).first()
    return float(row[0]), float(row[1]), float(row[2]), float(row[3])


def _categories(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT id, decay_tau_m, default_radius_m, scoring_weights FROM franchise_categories"
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def build(db: Session) -> Baselines:
    b = Baselines()
    b.density = sorted(
        float(x[0])
        for x in db.execute(text("SELECT density_per_km2 FROM demographics")).all()
    )
    b.pp = sorted(
        float(x[0])
        for x in db.execute(
            text("SELECT purchasing_power_index FROM demographics "
                 "WHERE purchasing_power_index IS NOT NULL")
        ).all()
    )

    xmin, ymin, xmax, ymax = _city_bbox(db)
    dx = (xmax - xmin) / SAMPLE_NX
    dy = (ymax - ymin) / SAMPLE_NY
    points = [
        (xmin + (i + 0.5) * dx, ymin + (j + 0.5) * dy)
        for i in range(SAMPLE_NX)
        for j in range(SAMPLE_NY)
    ]

    for cat in _categories(db):
        cid = cat["id"]
        tau = cat["decay_tau_m"]
        radius = cat["default_radius_m"]
        aw = cat["scoring_weights"]["anchor_type_weights"]
        cb = CatBaseline()
        for lng, lat in points:
            comps = geo.competitors_in_radius(db, lat, lng, cid, radius)
            cb.pressure.append(
                scoring.competitive_pressure(
                    [(c["distance_m"], c["is_chain"]) for c in comps], tau
                )
            )
            anchors = geo.anchors_in_radius(db, lat, lng, radius)
            cb.anchor_raw.append(
                scoring.anchor_raw([(a["distance_m"], a["anchor_type"]) for a in anchors], tau, aw)
            )
            nd = geo.nearest_competitor_distance(db, lat, lng, cid)
            if nd is not None:
                cb.nearest.append(nd)
            region = geo.point_in_region(db, lat, lng)
            if region:
                demo = geo.get_demographics(db, region["id"])
                if demo and demo["population"]:
                    cb.per_capita.append(len(comps) / demo["population"])
        cb.pressure.sort()
        cb.per_capita.sort()
        cb.nearest.sort()
        cb.anchor_raw.sort()
        b.per_category[cid] = cb
    return b


def get(db: Session) -> Baselines:
    global _store
    if _store is None:
        _store = build(db)
    return _store


def reset() -> None:
    global _store
    _store = None
