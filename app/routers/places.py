from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(tags=["places"])

_POINT = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"


@router.get("/places")
def places(
    lat: float,
    lng: float,
    radius_m: int = 1000,
    category_id: int | None = None,
    place_type: str = "competitor",
    db: Session = Depends(get_db),
) -> dict:
    """Map overlay as a GeoJSON FeatureCollection (api-contract.md §3)."""
    clauses = ["p.place_type = :ptype", "p.is_active", f"ST_DWithin(p.location, {_POINT}, :radius)"]
    params = {"lng": lng, "lat": lat, "radius": radius_m, "ptype": place_type}
    if place_type == "competitor" and category_id is not None:
        clauses.append("p.category_id = :cat")
        params["cat"] = category_id
    where = " AND ".join(clauses)

    rows = db.execute(
        text(
            f"""
            SELECT p.id, p.name, p.place_type, p.anchor_type, p.rating,
                   b.name AS brand, COALESCE(b.is_chain, false) AS is_chain,
                   ST_Y(p.location::geometry) AS lat, ST_X(p.location::geometry) AS lng,
                   ST_Distance(p.location, {_POINT}) AS distance_m
            FROM places p
            LEFT JOIN brands b ON b.id = p.brand_id
            WHERE {where}
            ORDER BY distance_m
            """
        ),
        params,
    ).mappings().all()

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
            "properties": {
                "id": r["id"],
                "name": r["name"],
                "place_type": r["place_type"],
                "brand": r["brand"],
                "is_chain": r["is_chain"],
                "rating": float(r["rating"]) if r["rating"] is not None else None,
                "distance_m": round(r["distance_m"]),
                "anchor_type": r["anchor_type"],
            },
        }
        for r in rows
    ]
    return {"type": "FeatureCollection", "features": features}
