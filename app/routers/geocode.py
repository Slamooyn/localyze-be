from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import geo

router = APIRouter(tags=["geocode"])


@router.get("/geocode")
def geocode(q: str, db: Session = Depends(get_db)) -> list[dict]:
    """Search-as-you-type over local regions + place names. No external API."""
    q = q.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    results: list[dict] = []

    regions = db.execute(
        text(
            "SELECT id, name, level, "
            "ST_Y(centroid::geometry) AS lat, ST_X(centroid::geometry) AS lng "
            "FROM regions WHERE name ILIKE :p AND level IN ('district','subdistrict') "
            "ORDER BY (level='district') DESC, name LIMIT 6"
        ),
        {"p": pattern},
    ).mappings().all()
    for r in regions:
        results.append(
            {
                "label": f"{r['name']}, Jakarta Selatan",
                "lat": r["lat"],
                "lng": r["lng"],
                "type": "region",
                "region_id": r["id"],
            }
        )

    places = db.execute(
        text(
            "SELECT id, name, "
            "ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
            "FROM places WHERE name ILIKE :p AND is_active ORDER BY name LIMIT 6"
        ),
        {"p": pattern},
    ).mappings().all()
    for p in places:
        results.append(
            {
                "label": p["name"],
                "lat": p["lat"],
                "lng": p["lng"],
                "type": "place",
                "region_id": None,
            }
        )
    return results[:10]


@router.get("/reverse-geocode")
def reverse_geocode(lat: float, lng: float, db: Session = Depends(get_db)) -> dict:
    region = geo.point_in_region(db, lat, lng)
    if region is None:
        raise HTTPException(
            422,
            detail={
                "code": "OUT_OF_COVERAGE",
                "message": "Lokasi di luar wilayah pilot (Jakarta Selatan)",
            },
        )
    return {
        "region_id": region["id"],
        "name": region["name"],
        "level": region["level"],
        "address_approx": f"{region['name']}, Jakarta Selatan",
    }
