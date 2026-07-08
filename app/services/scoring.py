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


@dataclass
class ConfidenceCtx:
    has_demographics: bool = True
    pp_is_modeled: bool = False
    snapshot_age_days: int = 0
    competitor_count: int = 0
    region_level: str = "subdistrict"


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
