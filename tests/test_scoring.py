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
