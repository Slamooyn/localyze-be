"""Precompute score_grid_cells (~300 m cells) covering the pilot city per category.

Runs as the final seed step (scoring-algorithm.md §8). Reuses analyze.score_point
so grid scores match live analyses. Cannibalization is excluded (it is per-user).
"""
from __future__ import annotations

import math

from geoalchemy2.elements import WKTElement
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import FranchiseCategory, ScoreGridCell
from app.seed.geobuild import point_wkt
from app.services import analyze, baseline
from app.services.geohash import encode

STEP_M = 300


def _district_id(db: Session, lat: float, lng: float) -> int | None:
    row = db.execute(
        text(
            "SELECT id FROM regions WHERE level='district' "
            "AND ST_Contains(boundary, ST_SetSRID(ST_MakePoint(:lng,:lat),4326)) LIMIT 1"
        ),
        {"lng": lng, "lat": lat},
    ).first()
    return int(row[0]) if row else None


def build_grid(db: Session) -> None:
    baseline.reset()
    baseline.get(db)  # ensure baselines are fresh after (re)seed

    row = db.execute(
        text(
            "SELECT ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g) FROM "
            "(SELECT boundary::geometry g FROM regions WHERE level='city' LIMIT 1) t"
        )
    ).first()
    xmin, ymin, xmax, ymax = (float(v) for v in row)
    mid_lat = (ymin + ymax) / 2
    dlat = STEP_M / 111000.0
    dlng = STEP_M / (111000.0 * math.cos(math.radians(mid_lat)))

    cats = db.query(FranchiseCategory).all()

    lat = ymin + dlat / 2
    seen: set[tuple[int, str]] = set()
    batch = 0
    while lat < ymax:
        lng = xmin + dlng / 2
        while lng < xmax:
            district_id = _district_id(db, lat, lng)
            if district_id is not None:
                gh = encode(lat, lng, 7)
                for cat in cats:
                    key = (cat.id, gh)
                    if key in seen:
                        continue
                    scored = analyze.score_point(db, lat, lng, cat)
                    if scored is None:
                        continue
                    composite, demand, competition = scored
                    seen.add(key)
                    db.add(
                        ScoreGridCell(
                            category_id=cat.id,
                            region_id=district_id,
                            centroid=WKTElement(point_wkt(lng, lat), srid=4326),
                            geohash=gh,
                            score_composite=composite,
                            score_demand=demand,
                            score_competition=competition,
                        )
                    )
                    batch += 1
                    if batch % 2000 == 0:
                        db.commit()
            lng += dlng
        lat += dlat
    db.commit()
