"""Seed the demo account: demo@localyze.id / demo1234 with 2 analyses + 3 outlets."""
from __future__ import annotations

import uuid

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Analysis, FranchiseCategory, User, UserOutlet
from app.services import analyze as analyze_svc
from app.services import security

DEMO_EMAIL = "demo@localyze.id"
DEMO_PASSWORD = "demo1234"

# (name, lat, lng, category_slug) — one strong candidate + one saturated (cautionary)
DEMO_ANALYSES = [
    ("Kandidat Prime — Tebet Timur", -6.2393, 106.8388, "coffee-grab-go"),
    ("Tebet Raya (pasar jenuh)", -6.2264, 106.8531, "coffee-grab-go"),
]

# outlets near Tebet (name, lat, lng)
DEMO_OUTLETS = [
    ("Cabang Tebet Timur", -6.2270, 106.8535),
    ("Cabang Kebon Baru", -6.2300, 106.8500),
    ("Cabang Menteng Dalam", -6.2210, 106.8480),
]


def build_demo(db: Session) -> None:
    demo = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if demo is None:
        demo = User(
            name="Akun Demo",
            email=DEMO_EMAIL,
            password_hash=security.hash_password(DEMO_PASSWORD),
        )
        db.add(demo)
        db.commit()
        db.refresh(demo)

    # outlets first, so the second analysis reflects cannibalization
    batch = uuid.uuid4().hex
    for name, lat, lng in DEMO_OUTLETS:
        db.add(
            UserOutlet(
                user_id=demo.id,
                name=name,
                location=WKTElement(f"POINT({lng} {lat})", srid=4326),
                address="Jakarta Selatan",
                import_batch=batch,
            )
        )
    db.commit()

    for name, lat, lng, slug in DEMO_ANALYSES:
        cat = db.scalar(select(FranchiseCategory).where(FranchiseCategory.slug == slug))
        res = analyze_svc.run_analysis(
            db, lat, lng, cat, include_cannibalization=True, user_id=demo.id
        )
        f = res["_db"]
        db.add(
            Analysis(
                name=name,
                user_id=demo.id,
                category_id=cat.id,
                location=WKTElement(f"POINT({lng} {lat})", srid=4326),
                address=f["address"],
                region_id=f["region_id"],
                radius_m=res["radius_m"],
                score_composite=f["score_composite"],
                score_demand=f["score_demand"],
                score_competition=f["score_competition"],
                cannibalization_penalty=f["cannibalization_penalty"],
                verdict=f["verdict"],
                confidence=f["confidence"],
                breakdown=res["breakdown"],
            )
        )
    db.commit()
