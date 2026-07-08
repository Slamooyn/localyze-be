from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FranchiseCategory
from app.schemas import CategoryOut

router = APIRouter(tags=["meta"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryOut]:
    cats = db.scalars(select(FranchiseCategory).order_by(FranchiseCategory.id)).all()
    return [
        CategoryOut(
            id=c.id,
            slug=c.slug,
            name=c.name,
            default_radius_m=c.default_radius_m,
            decay_tau_m=c.decay_tau_m,
            pillar_weights=c.scoring_weights["pillars"],
        )
        for c in cats
    ]
