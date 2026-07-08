from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Demographics, Region
from app.schemas import RegionOut

router = APIRouter(tags=["regions"])


@router.get("/regions", response_model=list[RegionOut])
def list_regions(
    level: str | None = None, db: Session = Depends(get_db)
) -> list[RegionOut]:
    stmt = select(Region)
    if level:
        stmt = stmt.where(Region.level == level)
    stmt = stmt.order_by(Region.name)
    return [
        RegionOut(
            id=r.id, bps_code=r.bps_code, name=r.name, level=r.level, parent_id=r.parent_id
        )
        for r in db.scalars(stmt).all()
    ]


@router.get("/regions/{region_id}/demographics")
def region_demographics(region_id: int, db: Session = Depends(get_db)) -> dict:
    region = db.get(Region, region_id)
    if region is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Region tidak ditemukan"})
    demo = db.scalar(select(Demographics).where(Demographics.region_id == region_id))
    if demo is None:
        raise HTTPException(
            404, detail={"code": "NO_DEMOGRAPHICS", "message": "Demografi tidak tersedia"}
        )
    return {
        "region": {"id": region.id, "name": region.name, "level": region.level},
        "population": demo.population,
        "density_per_km2": float(demo.density_per_km2),
        "age_distribution": demo.age_distribution,
        "purchasing_power_index": float(demo.purchasing_power_index)
        if demo.purchasing_power_index is not None
        else None,
        "is_modeled": demo.is_modeled,
        "data_year": demo.data_year,
        "source": demo.source,
    }
