"""Categories, brands, and place generation (clustered competitors + real anchors)."""
from __future__ import annotations

import json
import random
from pathlib import Path

from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.models import Brand, FranchiseCategory, Place
from app.seed import config as C
from app.seed.geobuild import point_wkt

DATA_DIR = Path(__file__).parent / "data"


def build_categories(db: Session) -> dict[str, FranchiseCategory]:
    out: dict[str, FranchiseCategory] = {}
    for cat in C.CATEGORIES:
        obj = FranchiseCategory(
            slug=cat["slug"],
            name=cat["name"],
            google_place_types=cat["google_place_types"],
            decay_tau_m=cat["decay_tau_m"],
            default_radius_m=cat["default_radius_m"],
            scoring_weights=cat["scoring_weights"],
            target_demo_profile=cat["target_demo_profile"],
        )
        db.add(obj)
        db.flush()
        out[obj.slug] = obj
    db.commit()
    return out


def build_brands(
    db: Session, cats: dict[str, FranchiseCategory]
) -> dict[str, list[Brand]]:
    brands = json.loads((DATA_DIR / "brands.json").read_text())
    by_cat: dict[str, list[Brand]] = {slug: [] for slug in cats}
    for b in brands:
        cat = cats[b["category_slug"]]
        obj = Brand(name=b["name"], category_id=cat.id, is_chain=b["is_chain"])
        db.add(obj)
        db.flush()
        by_cat[b["category_slug"]].append(obj)
    db.commit()
    return by_cat


def _sample_on_corridor(rng: random.Random) -> tuple[float, float]:
    corridor = rng.choice(C.CORRIDORS)
    i = rng.randrange(len(corridor) - 1)
    (x1, y1), (x2, y2) = corridor[i], corridor[i + 1]
    t = rng.random()
    return x1 + t * (x2 - x1), y1 + t * (y2 - y1)


def _jitter(lng: float, lat: float, meters: float, rng: random.Random) -> tuple[float, float]:
    import math

    dx = rng.gauss(0, meters)
    dy = rng.gauss(0, meters)
    dlat = dy / 111000.0
    dlng = dx / (111000.0 * math.cos(math.radians(lat)))
    return lng + dlng, lat + dlat


def build_places(
    db: Session,
    cats: dict[str, FranchiseCategory],
    brands_by_cat: dict[str, list[Brand]],
) -> None:
    rng = random.Random(42)
    bbox = C.BBOX

    # --- competitors, clustered on commercial corridors ---
    for slug, share in C.CATEGORY_MIX.items():
        cat = cats[slug]
        count = round(C.TOTAL_COMPETITORS * share)
        brand_pool = brands_by_cat[slug]
        for _ in range(count):
            if rng.random() < 0.80:
                lng, lat = _sample_on_corridor(rng)
                lng, lat = _jitter(lng, lat, 280, rng)
            else:
                lng = rng.uniform(bbox["west"], bbox["east"])
                lat = rng.uniform(bbox["south"], bbox["north"])
            lng = min(bbox["east"], max(bbox["west"], lng))
            lat = min(bbox["north"], max(bbox["south"], lat))
            brand = rng.choice(brand_pool)
            db.add(
                Place(
                    external_id=None,
                    name=f"{brand.name} {rng.randint(1, 99)}",
                    place_type="competitor",
                    category_id=cat.id,
                    brand_id=brand.id,
                    anchor_type=None,
                    location=WKTElement(point_wkt(lng, lat), srid=4326),
                    address="Jakarta Selatan",
                    rating=round(rng.uniform(3.7, 4.9), 1),
                    rating_count=rng.randint(20, 1500),
                    price_level=rng.randint(1, 3),
                    source="seed",
                    snapshot_date=C.SNAPSHOT_DATE,
                    is_active=True,
                )
            )
    db.commit()

    # --- anchors, from curated real coordinates ---
    anchors = json.loads((DATA_DIR / "anchors.json").read_text())
    for a in anchors:
        db.add(
            Place(
                external_id=None,
                name=a["name"],
                place_type="anchor",
                category_id=None,
                brand_id=None,
                anchor_type=a["anchor_type"],
                location=WKTElement(point_wkt(a["lng"], a["lat"]), srid=4326),
                address="Jakarta Selatan",
                source="manual",
                snapshot_date=C.SNAPSHOT_DATE,
                is_active=True,
            )
        )
    db.commit()
