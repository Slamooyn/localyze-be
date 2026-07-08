from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db

router = APIRouter(tags=["meta"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {"status": "ok", "db": db_status, "seed_version": settings.seed_version}
