from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.scoring import to_verdict

router = APIRouter(tags=["discovery"])


@router.get("/discovery")
def discovery(
    category_slug: str,
    region_id: int = Query(..., description="kecamatan (level=district)"),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
) -> dict:
    cat = db.execute(
        text("SELECT id, name FROM franchise_categories WHERE slug = :s"),
        {"s": category_slug},
    ).mappings().first()
    if cat is None:
        raise HTTPException(
            404, detail={"code": "CATEGORY_NOT_FOUND", "message": "Kategori tidak dikenal"}
        )

    cells = db.execute(
        text(
            """
            SELECT g.id, g.score_composite, g.score_demand, g.score_competition,
                   g.computed_at, r.name AS region_name,
                   ST_Y(g.centroid::geometry) AS lat, ST_X(g.centroid::geometry) AS lng
            FROM score_grid_cells g
            LEFT JOIN regions r ON r.id = g.region_id
            WHERE g.category_id = :cat AND g.region_id = :rid
            ORDER BY g.score_composite DESC
            """
        ),
        {"cat": cat["id"], "rid": region_id},
    ).mappings().all()

    if not cells:
        raise HTTPException(
            404,
            detail={"code": "NO_GRID", "message": "Belum ada grid untuk wilayah/kategori ini"},
        )

    top = [
        {
            "rank": i + 1,
            "cell_id": c["id"],
            "centroid": {"lat": c["lat"], "lng": c["lng"]},
            "region_name": c["region_name"],
            "score_composite": float(c["score_composite"]),
            "score_demand": float(c["score_demand"]),
            "score_competition": float(c["score_competition"]),
            "verdict": to_verdict(float(c["score_composite"])),
        }
        for i, c in enumerate(cells[:limit])
    ]
    heatmap = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c["lng"], c["lat"]]},
                "properties": {"score": float(c["score_composite"])},
            }
            for c in cells
        ],
    }
    computed_at = max(c["computed_at"] for c in cells).isoformat()
    return {"top_locations": top, "heatmap": heatmap, "computed_at": computed_at}
