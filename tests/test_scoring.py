"""Unit tests for the pure scoring core (no DB)."""
from app.services import scoring as s


def test_distance_decay_closer_outweighs_farther():
    tau = 600
    assert s.decay_weight(200, tau) > s.decay_weight(2000, tau)
    # a chain competitor at 200m should dominate a far independent one
    near = s.competitive_pressure([(200, True)], tau)
    far = s.competitive_pressure([(2000, False)], tau)
    assert near > far


def test_percentile_monotonic_and_clamped():
    base = sorted([1.0, 2.0, 3.0, 4.0, 5.0])
    p_lo = s.percentile(0.0, base)
    p_mid = s.percentile(3.0, base)
    p_hi = s.percentile(99.0, base)
    assert p_lo == 0.0
    assert p_hi == 100.0
    assert p_lo <= p_mid <= p_hi
    # strictly non-decreasing across the range
    prev = -1.0
    for v in [0, 1, 2, 3, 4, 5, 6]:
        cur = s.percentile(v, base)
        assert cur >= prev
        prev = cur


def test_percentile_empty_baseline_is_neutral():
    assert s.percentile(10.0, []) == 50.0


def test_verdict_band_boundaries():
    assert s.to_verdict(79.99) == "strong"
    assert s.to_verdict(80.0) == "prime"
    assert s.to_verdict(65.0) == "strong"
    assert s.to_verdict(64.99) == "conditional"
    assert s.to_verdict(50.0) == "conditional"
    assert s.to_verdict(49.99) == "avoid"


def test_cannibalization_zero_without_outlets():
    penalty, affected = s.cannibalization([], max_penalty=15, tau_m=1200)
    assert penalty == 0.0
    assert affected == []


def test_cannibalization_capped_at_max_penalty():
    # many outlets right on top of the site -> overlap huge -> capped
    outlets = [{"id": i, "name": f"o{i}", "distance_m": 5} for i in range(20)]
    penalty, affected = s.cannibalization(outlets, max_penalty=15, tau_m=1200)
    assert penalty == 15.0
    assert len(affected) == 20


def test_demographic_match_bounds():
    age = {"0_14": 0.2, "15_24": 0.2, "25_34": 0.2, "35_54": 0.2, "55_plus": 0.2}
    target = {"15_24": 0.35, "25_34": 0.35, "35_54": 0.20, "55_plus": 0.10}
    m = s.demographic_match(age, target)
    assert 0.0 <= m <= 100.0


def test_contribution_sign():
    # above-neutral factor contributes positively, below-neutral negatively
    assert s.contribution(0.55, 0.25, 78) > 0
    assert s.contribution(0.45, 0.50, 15) < 0


def test_make_factor_has_full_contract():
    f = s.make_factor(
        key="population_density",
        label="Kepadatan penduduk",
        raw_value=15234,
        unit="jiwa/km²",
        pct=78,
        weight=0.30,
        pillar_weight=0.55,
        score=78,
        evidence="15.234 jiwa/km² — persentil ke-78",
    )
    for field in ("raw_value", "percentile", "weight", "contribution", "evidence"):
        assert field in f
    assert f["percentile"] == 78


def test_weighted_sum():
    weights = {"a": 0.5, "b": 0.5}
    scores = {"a": 80.0, "b": 40.0}
    assert s.weighted_sum(weights, scores) == 60.0


# --- Phase 2 (Wave 2A): disaster penalty + synergy bonus -----------------
SYNERGY_MAP = {
    "complementary": [
        {"match": {"anchor_type": "office"}, "weight": 1.0, "opportunity": "B2B"},
        {"match": {"anchor_type": "campus"}, "weight": 0.8, "opportunity": "Mahasiswa"},
    ],
    "max_bonus": 5,
}


def test_disaster_penalty_monotonic_in_level():
    prev = -1.0
    for level in (1, 2, 3, 4, 5):
        p, missing = s.disaster_penalty([("flood", level)])
        assert not missing
        assert p >= prev
        prev = p
    assert s.disaster_penalty([("flood", 1)])[0] == 0.0
    assert s.disaster_penalty([("flood", 5)])[0] == 10.0  # full range 0..10


def test_disaster_penalty_takes_worst_weighted_hazard_not_sum():
    p_flood, _ = s.disaster_penalty([("flood", 4)])
    p_quake, _ = s.disaster_penalty([("earthquake", 4)])
    assert p_flood > p_quake  # flood weighted 1.0 vs earthquake 0.6
    combined, _ = s.disaster_penalty(
        [("flood", 4), ("earthquake", 4), ("landslide", 2)]
    )
    assert combined == p_flood  # max over hazards, not Σ


def test_disaster_penalty_no_data_flags_missing():
    p, missing = s.disaster_penalty([])
    assert p == 0.0
    assert missing is True


def test_confidence_drops_when_risk_data_missing():
    base = s.confidence(s.ConfidenceCtx(competitor_count=5))
    flagged = s.confidence(
        s.ConfidenceCtx(competitor_count=5, risk_data_missing=True)
    )
    assert flagged == round(base - s.RISK_DATA_MISSING_CONFIDENCE_DROP, 2)


def test_synergy_bonus_capped_at_max_bonus():
    anchors = [(10.0, "office")] * 50  # huge raw sum -> must cap
    bonus, groups = s.synergy_bonus(anchors, SYNERGY_MAP, tau_m=600)
    assert bonus == 5.0
    assert groups[0]["type"] == "office"
    assert groups[0]["count"] == 50


def test_synergy_bonus_zero_without_complementary_matches():
    bonus, groups = s.synergy_bonus([(100.0, "school")], SYNERGY_MAP, tau_m=600)
    assert bonus == 0.0
    assert groups == []


def test_synergy_bonus_groups_carry_contract_fields():
    anchors = [(240.0, "office"), (400.0, "office"), (150.0, "campus")]
    bonus, groups = s.synergy_bonus(anchors, SYNERGY_MAP, tau_m=600)
    assert 0.0 < bonus <= 5.0
    by_type = {g["type"]: g for g in groups}
    assert by_type["office"]["count"] == 2
    assert by_type["office"]["nearest_m"] == 240
    for g in groups:
        for field in ("type", "count", "nearest_m", "weight_sum", "opportunity"):
            assert field in g


def test_composite_v2_clamped_with_modifiers():
    # weak pillars + max cannibalization + max disaster -> floor at 0
    assert s.clamp(0.5 * 10 + 0.5 * 10 - 15 - 10 + 0) == 0.0
    # strong pillars + max synergy bonus -> ceiling at 100
    assert s.clamp(0.5 * 100 + 0.5 * 100 - 0 - 0 + 5) == 100.0
