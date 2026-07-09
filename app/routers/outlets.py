from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from geoalchemy2.elements import WKTElement
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserOutlet
from app.services.security import get_current_user

router = APIRouter(tags=["outlets"])

REQUIRED_HEADERS = {"name", "lat", "lng"}


@router.post("/outlets/import")
async def import_outlets(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if reader.fieldnames is None or not REQUIRED_HEADERS <= {
        (h or "").strip().lower() for h in reader.fieldnames
    }:
        raise HTTPException(
            400,
            detail={
                "code": "BAD_CSV_HEADER",
                "message": "Header wajib: name,lat,lng,address",
            },
        )

    batch = uuid.uuid4().hex
    imported = 0
    skipped: list[dict] = []
    # row 1 = header; data rows start at 2
    for i, row in enumerate(reader, start=2):
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        name = norm.get("name", "")
        if not name:
            skipped.append({"row": i, "reason": "missing name"})
            continue
        try:
            lat = float(norm.get("lat", ""))
        except ValueError:
            skipped.append({"row": i, "reason": "invalid lat"})
            continue
        try:
            lng = float(norm.get("lng", ""))
        except ValueError:
            skipped.append({"row": i, "reason": "invalid lng"})
            continue
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            skipped.append({"row": i, "reason": "coordinate out of range"})
            continue
        db.add(
            UserOutlet(
                user_id=user.id,
                name=name,
                location=WKTElement(f"POINT({lng} {lat})", srid=4326),
                address=norm.get("address") or None,
                import_batch=batch,
            )
        )
        imported += 1

    db.commit()
    return {"import_batch": batch, "imported": imported, "skipped": skipped}


@router.get("/outlets")
def list_outlets(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    rows = db.execute(
        text(
            "SELECT id, name, address, import_batch, "
            "ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
            "FROM user_outlets WHERE user_id = :uid ORDER BY created_at DESC"
        ),
        {"uid": str(user.id)},
    ).mappings().all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
                "properties": {
                    "id": r["id"],
                    "name": r["name"],
                    "address": r["address"],
                    "import_batch": r["import_batch"],
                },
            }
            for r in rows
        ],
    }


@router.delete("/outlets", status_code=200)
def delete_outlets(
    import_batch: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    q = db.query(UserOutlet).filter(UserOutlet.user_id == user.id)
    if import_batch:
        q = q.filter(UserOutlet.import_batch == import_batch)
    n = q.delete()
    db.commit()
    return {"deleted": n}
