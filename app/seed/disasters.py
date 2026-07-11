"""Disaster risks per kecamatan (Phase 2 Wave 2A — phase2-backend-spec.md §1.1).

Levels come from app.seed.config.DISASTER_RISKS (keyed by kecamatan name) with the
source labeled per row ('modeled-v1' fallback — see the note in config). One row per
(region, hazard); UNIQUE(region_id, hazard) guards against duplicates.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DisasterRisk, Region
from app.seed import config as C


def build_disaster_risks(db: Session) -> None:
    districts = (
        db.execute(select(Region).where(Region.level == "district")).scalars().all()
    )
    for region in districts:
        levels = C.DISASTER_RISKS.get(region.name)
        if levels is None:
            continue  # kecamatan without data -> no rows (scoring flags data_missing)
        for hazard, level in levels.items():
            db.add(
                DisasterRisk(
                    region_id=region.id,
                    hazard=hazard,
                    level=level,
                    source=C.DISASTER_SOURCE,
                    data_year=C.DISASTER_DATA_YEAR,
                )
            )
    db.commit()
