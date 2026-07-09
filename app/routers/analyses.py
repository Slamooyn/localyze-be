from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from geoalchemy2.elements import WKTElement
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Analysis, FranchiseCategory, Region, User
from app.schemas import AnalyzeRequest, PatchAnalysisRequest
from app.services import analyze as analyze_svc
from app.services.security import get_current_user

router = APIRouter(tags=["analyses"])


def _latlng(db: Session, analysis_id) -> tuple[float, float]:
    row = db.execute(
        text(
            "SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng "
            "FROM analyses WHERE id = :id"
        ),
        {"id": str(analysis_id)},
    ).mappings().first()
    return row["lat"], row["lng"]


def _payload(db: Session, a: Analysis) -> dict:
    lat, lng = _latlng(db, a.id)
    cat = db.get(FranchiseCategory, a.category_id)
    region = db.get(Region, a.region_id) if a.region_id else None
    return {
        "id": str(a.id),
        "name": a.name,
        "location": {"lat": lat, "lng": lng},
        "region": {"id": region.id, "name": region.name} if region else None,
        "category": {"slug": cat.slug, "name": cat.name},
        "radius_m": a.radius_m,
        "score": {
            "composite": float(a.score_composite),
            "demand": float(a.score_demand),
            "competition": float(a.score_competition),
            "cannibalization_penalty": float(a.cannibalization_penalty),
            "verdict": a.verdict,
            "confidence": float(a.confidence),
        },
        "breakdown": a.breakdown,
        "created_at": a.created_at.isoformat(),
    }


@router.post("/analyses", status_code=201)
def create_analysis(
    req: AnalyzeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    cat = db.scalar(select(FranchiseCategory).where(FranchiseCategory.slug == req.category_slug))
    if cat is None:
        raise HTTPException(
            404, detail={"code": "CATEGORY_NOT_FOUND", "message": "Kategori tidak dikenal"}
        )
    try:
        res = analyze_svc.run_analysis(
            db, req.lat, req.lng, cat, req.radius_m, req.include_cannibalization, user_id=user.id
        )
    except analyze_svc.OutOfCoverage:
        raise HTTPException(
            422,
            detail={
                "code": "OUT_OF_COVERAGE",
                "message": "Lokasi di luar wilayah pilot (Jakarta Selatan)",
            },
        )

    db_fields = res["_db"]
    name = req.name or f"{res['region']['name']}, Jakarta Selatan"
    a = Analysis(
        name=name,
        user_id=user.id,
        category_id=cat.id,
        location=WKTElement(f"POINT({req.lng} {req.lat})", srid=4326),
        address=db_fields["address"],
        region_id=db_fields["region_id"],
        radius_m=res["radius_m"],
        score_composite=db_fields["score_composite"],
        score_demand=db_fields["score_demand"],
        score_competition=db_fields["score_competition"],
        cannibalization_penalty=db_fields["cannibalization_penalty"],
        verdict=db_fields["verdict"],
        confidence=db_fields["confidence"],
        breakdown=res["breakdown"],
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _payload(db, a)


@router.get("/analyses")
def list_analyses(
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = db.scalars(
        select(Analysis)
        .where(Analysis.user_id == user.id)
        .order_by(Analysis.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    out = []
    for a in rows:
        lat, lng = _latlng(db, a.id)
        cat = db.get(FranchiseCategory, a.category_id)
        out.append(
            {
                "id": str(a.id),
                "name": a.name,
                "location": {"lat": lat, "lng": lng},
                "category": {"slug": cat.slug, "name": cat.name},
                "radius_m": a.radius_m,
                "score": {
                    "composite": float(a.score_composite),
                    "verdict": a.verdict,
                    "confidence": float(a.confidence),
                },
                "created_at": a.created_at.isoformat(),
            }
        )
    return out


@router.get("/analyses/compare")
def compare(
    ids: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    id_list = [s.strip() for s in ids.split(",") if s.strip()][:3]
    if len(id_list) < 2:
        raise HTTPException(
            400, detail={"code": "COMPARE_MIN", "message": "Minimal 2 analisis untuk dibandingkan"}
        )
    payloads = []
    for sid in id_list:
        a = _get_or_404(db, sid, user)
        payloads.append(_payload(db, a))

    best = max(payloads, key=lambda p: p["score"]["composite"])
    factor_winners: dict[str, str] = {}
    keys: set[str] = set()
    for p in payloads:
        for pillar in ("demand", "competition"):
            for f in p["breakdown"][pillar]["factors"]:
                keys.add(f["key"])
    for key in keys:
        winner = None
        best_contrib = None
        for p in payloads:
            for pillar in ("demand", "competition"):
                for f in p["breakdown"][pillar]["factors"]:
                    if f["key"] == key and (best_contrib is None or f["contribution"] > best_contrib):
                        best_contrib = f["contribution"]
                        winner = p["id"]
        if winner:
            factor_winners[key] = winner

    return {
        "analyses": payloads,
        "deltas": {"best_composite": best["id"], "factor_winners": factor_winners},
    }


def _get_or_404(db: Session, sid: str, user: User) -> Analysis:
    not_found = HTTPException(
        404, detail={"code": "NOT_FOUND", "message": "Analisis tidak ditemukan"}
    )
    try:
        uid = uuid.UUID(sid)
    except ValueError:
        raise not_found
    a = db.get(Analysis, uid)
    if a is None or a.user_id != user.id:  # other users' analyses are 404, not 403
        raise not_found
    return a


@router.get("/analyses/{analysis_id}")
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _payload(db, _get_or_404(db, analysis_id, user))


@router.patch("/analyses/{analysis_id}")
def patch_analysis(
    analysis_id: str,
    req: PatchAnalysisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    a = _get_or_404(db, analysis_id, user)
    a.name = req.name
    db.commit()
    db.refresh(a)
    return _payload(db, a)


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    a = _get_or_404(db, analysis_id, user)
    db.delete(a)
    db.commit()
    return Response(status_code=204)
