"""Analysis orchestrator — combines geo queries + baselines + pure scoring into
the full payload defined in api-contract.md §4 / database-schema.md §3.7."""
from __future__ import annotations

from datetime import date
from statistics import median

from sqlalchemy.orm import Session

from app.models import FranchiseCategory
from app.services import baseline, geo
from app.services import scoring as sc


class OutOfCoverage(Exception):
    pass


def _num(x) -> float:
    return float(x) if x is not None else 0.0


def run_analysis(
    db: Session,
    lat: float,
    lng: float,
    category: FranchiseCategory,
    radius_m: int | None = None,
    include_cannibalization: bool = True,
) -> dict:
    region = geo.point_in_region(db, lat, lng)
    if region is None:
        raise OutOfCoverage()

    demo = geo.get_demographics(db, region["id"])
    bl = baseline.get(db)
    cb = bl.per_category[category.id]

    tau = category.decay_tau_m
    radius = radius_m or category.default_radius_m
    weights = category.scoring_weights
    pillars = weights["pillars"]
    dfw = weights["demand_factors"]
    cfw = weights["competition_factors"]
    aw = weights["anchor_type_weights"]
    pw_d = pillars["demand"]
    pw_c = pillars["competition"]

    # ---------- DEMAND ----------
    density = _num(demo["density_per_km2"]) if demo else (median(bl.density) if bl.density else 0)
    d1_pct = sc.percentile(density, bl.density)
    d1 = d1_pct

    age = demo["age_distribution"] if demo else {}
    d2 = sc.demographic_match(age, category.target_demo_profile.get("age_weights", {}))

    pp_raw = demo["purchasing_power_index"] if demo else None
    pp_modeled = bool(demo["is_modeled"]) if demo else False
    if pp_raw is not None:
        d3_pct = sc.percentile(_num(pp_raw), bl.pp)
        d3 = d3_pct
    else:
        d3_pct = 50.0
        d3 = 50.0

    anchors = geo.anchors_in_radius(db, lat, lng, radius)
    araw = sc.anchor_raw([(a["distance_m"], a["anchor_type"]) for a in anchors], tau, aw)
    d4_pct = sc.percentile(araw, cb.anchor_raw)
    d4 = d4_pct

    demand_scores = {
        "population_density": d1,
        "demographic_match": d2,
        "purchasing_power": d3,
        "anchor_poi": d4,
    }
    demand = sc.weighted_sum(dfw, demand_scores)

    # ---------- COMPETITION ----------
    comps = geo.competitors_in_radius(db, lat, lng, category.id, radius)
    pressure = sc.competitive_pressure([(c["distance_m"], c["is_chain"]) for c in comps], tau)
    press_pct = sc.percentile(pressure, cb.pressure)
    c1 = 100.0 - press_pct

    if demo and demo["population"]:
        pcap = len(comps) / demo["population"]
        pcap_pct = sc.percentile(pcap, cb.per_capita)
    else:
        pcap_pct = 50.0
    c2 = 100.0 - pcap_pct

    nearest = geo.nearest_competitor_distance(db, lat, lng, category.id)
    near_pct = sc.percentile(nearest, cb.nearest) if nearest is not None else 100.0
    c3 = near_pct

    comp_scores = {
        "weighted_density": c1,
        "per_capita_intensity": c2,
        "nearest_distance": c3,
    }
    competition = sc.weighted_sum(cfw, comp_scores)

    # ---------- CANNIBALIZATION ----------
    penalty, affected = 0.0, []
    if include_cannibalization:
        canni = weights["cannibalization"]
        outlets = geo.user_outlets_within(db, lat, lng, 3 * canni["tau_m"])
        penalty, affected = sc.cannibalization(outlets, canni["max_penalty"], canni["tau_m"])

    composite = sc.clamp(pw_d * demand + pw_c * competition - penalty)
    verdict = sc.to_verdict(composite)

    snap = db_snapshot_date(db)
    age_days = (date.today() - snap).days if snap else 0
    conf = sc.confidence(
        sc.ConfidenceCtx(
            has_demographics=demo is not None,
            pp_is_modeled=pp_modeled,
            snapshot_age_days=age_days,
            competitor_count=len(comps),
            region_level=region["level"],
        )
    )

    # ---------- BREAKDOWN ----------
    demand_factors = [
        sc.make_factor(
            "population_density", "Kepadatan penduduk", round(density), "jiwa/km²",
            d1_pct, dfw["population_density"], pw_d, d1,
            f"{density:,.0f} jiwa/km² — persentil ke-{d1_pct:.0f} se-Jakarta Selatan".replace(",", "."),
        ),
        sc.make_factor(
            "demographic_match", "Kecocokan demografi", round(d2), "%",
            d2, dfw["demographic_match"], pw_d, d2,
            f"Struktur usia area cocok {d2:.0f}% dengan profil {category.name}",
        ),
        sc.make_factor(
            "purchasing_power", "Daya beli", round(_num(pp_raw), 2) if pp_raw is not None else None,
            "indeks", d3_pct, dfw["purchasing_power"], pw_d, d3,
            (
                f"Indeks daya beli {_num(pp_raw):.2f} (modeled) — persentil ke-{d3_pct:.0f}"
                if pp_raw is not None
                else "Data daya beli tidak tersedia — diasumsikan rata-rata kota"
            ),
            is_modeled=pp_modeled,
        ),
        sc.make_factor(
            "anchor_poi", "Anchor POI", len(anchors), "titik",
            d4_pct, dfw["anchor_poi"], pw_d, d4,
            f"{len(anchors)} anchor (mall/kantor/kampus/stasiun) dalam radius {radius} m",
        ),
    ]
    competition_factors = [
        sc.make_factor(
            "weighted_density", "Kepadatan kompetitor", round(pressure, 1),
            "kompetitor efektif", press_pct, cfw["weighted_density"], pw_c, c1,
            f"{pressure:.1f} kompetitor efektif dalam {radius} m "
            f"(persentil ke-{press_pct:.0f} terpadat)",
        ),
        sc.make_factor(
            "per_capita_intensity", "Intensitas per kapita", len(comps),
            "kompetitor/populasi", pcap_pct, cfw["per_capita_intensity"], pw_c, c2,
            f"{len(comps)} kompetitor untuk {demo['population'] if demo else 0:,} penduduk kelurahan".replace(",", "."),
        ),
        sc.make_factor(
            "nearest_distance", "Jarak kompetitor terdekat",
            round(nearest) if nearest is not None else None, "m",
            near_pct, cfw["nearest_distance"], pw_c, c3,
            (
                f"Kompetitor terdekat {nearest:.0f} m — persentil ke-{near_pct:.0f} (makin jauh makin baik)"
                if nearest is not None
                else "Tidak ada kompetitor kategori ini di area"
            ),
        ),
    ]
    competitors_in_radius = [
        {
            "place_id": c["id"],
            "name": c["name"],
            "distance_m": round(c["distance_m"]),
            "decay_weight": round(sc.decay_weight(c["distance_m"], tau), 2),
            "is_chain": c["is_chain"],
            "lat": c["lat"],
            "lng": c["lng"],
        }
        for c in comps
    ]

    breakdown = {
        "demand": {"score": round(demand, 1), "factors": demand_factors},
        "competition": {
            "score": round(competition, 1),
            "factors": competition_factors,
            "competitors_in_radius": competitors_in_radius,
        },
        "cannibalization": {"penalty": round(penalty, 2), "affected_outlets": affected},
        "data_completeness": {
            "demographics_available": demo is not None,
            "purchasing_power_modeled": pp_modeled,
            "competitor_snapshot_date": snap.isoformat() if snap else None,
        },
    }

    return {
        "location": {"lat": lat, "lng": lng},
        "region": {"id": region["id"], "name": region["name"], "level": region["level"]},
        "category": {"slug": category.slug, "name": category.name},
        "radius_m": radius,
        "score": {
            "composite": round(composite, 1),
            "demand": round(demand, 1),
            "competition": round(competition, 1),
            "cannibalization_penalty": round(penalty, 2),
            "verdict": verdict,
            "confidence": conf,
        },
        "breakdown": breakdown,
        "_db": {
            "region_id": region["id"],
            "score_composite": round(composite, 2),
            "score_demand": round(demand, 2),
            "score_competition": round(competition, 2),
            "cannibalization_penalty": round(penalty, 2),
            "verdict": verdict,
            "confidence": conf,
            "address": region["name"],
        },
    }


def score_point(
    db: Session,
    lat: float,
    lng: float,
    category: FranchiseCategory,
    radius_m: int | None = None,
) -> tuple[float, float, float] | None:
    """Lean scorer for the discovery grid — returns (composite, demand, competition)
    with no cannibalization and no breakdown construction. Reuses the same pure
    scoring functions as run_analysis so the grid is consistent with live analyses."""
    region = geo.point_in_region(db, lat, lng)
    if region is None:
        return None
    demo = geo.get_demographics(db, region["id"])
    bl = baseline.get(db)
    cb = bl.per_category[category.id]

    tau = category.decay_tau_m
    radius = radius_m or category.default_radius_m
    w = category.scoring_weights
    dfw, cfw, aw, pillars = (
        w["demand_factors"],
        w["competition_factors"],
        w["anchor_type_weights"],
        w["pillars"],
    )

    density = _num(demo["density_per_km2"]) if demo else (median(bl.density) if bl.density else 0)
    d1 = sc.percentile(density, bl.density)
    d2 = sc.demographic_match(
        demo["age_distribution"] if demo else {},
        category.target_demo_profile.get("age_weights", {}),
    )
    pp_raw = demo["purchasing_power_index"] if demo else None
    d3 = sc.percentile(_num(pp_raw), bl.pp) if pp_raw is not None else 50.0
    anchors = geo.anchors_in_radius(db, lat, lng, radius)
    araw = sc.anchor_raw([(a["distance_m"], a["anchor_type"]) for a in anchors], tau, aw)
    d4 = sc.percentile(araw, cb.anchor_raw)
    demand = sc.weighted_sum(
        dfw,
        {"population_density": d1, "demographic_match": d2, "purchasing_power": d3, "anchor_poi": d4},
    )

    comps = geo.competitors_in_radius(db, lat, lng, category.id, radius)
    pressure = sc.competitive_pressure([(c["distance_m"], c["is_chain"]) for c in comps], tau)
    c1 = 100.0 - sc.percentile(pressure, cb.pressure)
    if demo and demo["population"]:
        c2 = 100.0 - sc.percentile(len(comps) / demo["population"], cb.per_capita)
    else:
        c2 = 50.0
    nearest = geo.nearest_competitor_distance(db, lat, lng, category.id)
    c3 = sc.percentile(nearest, cb.nearest) if nearest is not None else 100.0
    competition = sc.weighted_sum(
        cfw,
        {"weighted_density": c1, "per_capita_intensity": c2, "nearest_distance": c3},
    )

    composite = sc.clamp(pillars["demand"] * demand + pillars["competition"] * competition)
    return round(composite, 2), round(demand, 2), round(competition, 2)


def db_snapshot_date(db: Session) -> date | None:
    from sqlalchemy import text

    row = db.execute(text("SELECT max(snapshot_date) FROM places")).first()
    return row[0] if row and row[0] else None
