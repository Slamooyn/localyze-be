"""Localyze scoring — PURE functions (no I/O).

Direct implementation of scoring-algorithm.md. Everything here takes plain data
via parameters so it can be unit-tested without a database. All sub-scores are
0-100 and "searah" (higher = better) so pillars combine cleanly.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

VERDICT_BANDS = [(80.0, "prime"), (65.0, "strong"), (50.0, "conditional")]

# Phase 2 (Wave 2A) — disaster modifier parameters (phase2-backend-spec.md §2).
# Global across all categories, so they live as module constants like VERDICT_BANDS
# (category-specific parameters stay in the franchise_categories JSONB columns).
HAZARD_WEIGHTS = {"flood": 1.0, "earthquake": 0.6, "landslide": 0.5}
DISASTER_PENALTY_SCALE = 10.0  # P_disaster range 0..10
RISK_DATA_MISSING_CONFIDENCE_DROP = 0.05


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def decay_weight(distance_m: float, tau_m: float) -> float:
    """Distance decay exp(-d/τ). A competitor at 200m outweighs one at 2km."""
    return math.exp(-distance_m / tau_m)


def percentile(value: float, sorted_baseline: list[float]) -> float:
    """0-100 percentile of `value` in a sorted baseline. Values outside the
    baseline clamp to 0 / 100. Monotonic in `value`."""
    if not sorted_baseline:
        return 50.0
    idx = bisect.bisect_left(sorted_baseline, value)
    return clamp(100.0 * idx / len(sorted_baseline))


def demographic_match(age_dist: dict, target_weights: dict) -> float:
    """Weighted overlap between an area's age structure and the category's ideal
    profile, normalised to the theoretical max (all population in the top bucket)."""
    if not target_weights:
        return 50.0
    raw = sum(age_dist.get(k, 0.0) * w for k, w in target_weights.items())
    max_raw = max(target_weights.values())
    return clamp(100.0 * raw / max_raw) if max_raw else 50.0


def weighted_sum(weights: dict, scores: dict) -> float:
    """Σ weight_f × score_f over shared keys."""
    return sum(weights[k] * scores.get(k, 0.0) for k in weights)


def competitive_pressure(
    competitors: list[tuple[float, bool]], tau_m: float
) -> float:
    """Σ (chain? 1.5 : 1.0) × decay. `competitors` = [(distance_m, is_chain), …]."""
    return sum((1.5 if is_chain else 1.0) * decay_weight(d, tau_m) for d, is_chain in competitors)


def anchor_raw(
    anchors: list[tuple[float, str]], tau_m: float, anchor_weights: dict
) -> float:
    """Gravity of nearby anchors. `anchors` = [(distance_m, anchor_type), …]."""
    return sum(
        anchor_weights.get(atype, 0.0) * decay_weight(d, tau_m) for d, atype in anchors
    )


def cannibalization(
    outlets: list[dict], max_penalty: float, tau_m: float
) -> tuple[float, list[dict]]:
    """Penalty from a brand's own nearby outlets. `outlets` items need 'distance_m'
    (and optionally 'id','name'). Returns (penalty, affected[])."""
    overlap = sum(decay_weight(o["distance_m"], tau_m) for o in outlets)
    penalty = min(max_penalty, max_penalty * overlap)
    affected = [
        {
            "outlet_id": o.get("id"),
            "name": o.get("name"),
            "distance_m": round(o["distance_m"]),
            "overlap_pct": round(100 * decay_weight(o["distance_m"], tau_m)),
        }
        for o in outlets
        if o["distance_m"] < 2.5 * tau_m
    ]
    return round(penalty, 2), affected


def disaster_penalty(
    hazards: list[tuple[str, int]],
    hazard_weights: dict | None = None,
    scale: float = DISASTER_PENALTY_SCALE,
) -> tuple[float, bool]:
    """P_disaster 0..scale (phase2-backend-spec.md §2):
    max_over_hazards(level_norm × hazard_weight) × scale, level_norm = (level−1)/4.
    `hazards` = [(hazard, level 1-5), …]. Kecamatan without data → (0, data_missing=True)
    — the caller lowers confidence by RISK_DATA_MISSING_CONFIDENCE_DROP."""
    weights = HAZARD_WEIGHTS if hazard_weights is None else hazard_weights
    if not hazards:
        return 0.0, True
    worst = max(
        ((level - 1) / 4.0) * weights.get(hazard, 0.0) for hazard, level in hazards
    )
    return round(clamp(worst * scale, 0.0, scale), 2), False


def synergy_bonus(
    anchors: list[tuple[float, str]], synergy_map: dict, tau_m: float
) -> tuple[float, list[dict]]:
    """B_synergy 0..max_bonus (phase2-backend-spec.md §2):
    min(max_bonus, Σ weight_i × exp(−d_i/τ)) over complementary anchors in radius.
    `anchors` = [(distance_m, anchor_type), …]; `synergy_map` is the category JSONB.
    Returns (bonus, opportunities[]) — one group per matched complementary type with
    count / nearest_m / weight_sum / opportunity (evidence sentence added by caller)."""
    max_bonus = float(synergy_map.get("max_bonus", 5))
    total = 0.0
    groups: list[dict] = []
    for entry in synergy_map.get("complementary", []):
        atype = entry.get("match", {}).get("anchor_type")
        weight = float(entry.get("weight", 0.0))
        matched = [d for d, t in anchors if t == atype]
        if not matched:
            continue
        weight_sum = sum(weight * decay_weight(d, tau_m) for d in matched)
        total += weight_sum
        groups.append(
            {
                "type": atype,
                "count": len(matched),
                "nearest_m": round(min(matched)),
                "weight_sum": round(weight_sum, 2),
                "opportunity": entry.get("opportunity"),
            }
        )
    groups.sort(key=lambda g: g["weight_sum"], reverse=True)
    return round(min(max_bonus, total), 2), groups


@dataclass
class ConfidenceCtx:
    has_demographics: bool = True
    pp_is_modeled: bool = False
    snapshot_age_days: int = 0
    competitor_count: int = 0
    region_level: str = "subdistrict"
    risk_data_missing: bool = False  # Phase 2: kecamatan without disaster data


def confidence(ctx: ConfidenceCtx) -> float:
    score = 1.0
    if not ctx.has_demographics:
        score -= 0.40
    elif ctx.pp_is_modeled:
        score -= 0.10
    if ctx.snapshot_age_days > 180:
        score -= 0.15
    if ctx.competitor_count == 0:
        score -= 0.15
    if ctx.region_level == "district":
        score -= 0.10
    if ctx.risk_data_missing:
        score -= RISK_DATA_MISSING_CONFIDENCE_DROP
    return max(0.3, round(score, 2))


def to_verdict(score: float) -> str:
    for threshold, label in VERDICT_BANDS:
        if score >= threshold:
            return label
    return "avoid"


def contribution(pillar_weight: float, factor_weight: float, factor_score: float) -> float:
    """± points versus a neutral (score=50) location."""
    return round(pillar_weight * factor_weight * (factor_score - 50.0), 2)


def make_factor(
    key: str,
    label: str,
    raw_value: float,
    unit: str,
    pct: float,
    weight: float,
    pillar_weight: float,
    score: float,
    evidence: str,
    is_modeled: bool = False,
) -> dict:
    """Build one breakdown factor. Guarantees the FE contract fields."""
    f = {
        "key": key,
        "label": label,
        "raw_value": raw_value,
        "unit": unit,
        "percentile": round(pct),
        "weight": weight,
        "contribution": contribution(pillar_weight, weight, score),
        "evidence": evidence,
    }
    if is_modeled:
        f["is_modeled"] = True
    return f
