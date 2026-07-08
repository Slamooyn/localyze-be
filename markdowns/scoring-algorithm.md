# Localyze — Scoring Algorithm Spec

> **Status:** MVP spec · **Created:** 2026-07-08 · **Owner:** Moym
> **Prasyarat:** baca `database-schema.md` (struktur `scoring_weights`, `breakdown`)

---

## 1. Gambaran Umum

```
Localyze Score (0–100)
  = w_demand   × DemandIndex
  + w_compete  × CompetitionIndex        ← sudah inverted: tinggi = kompetisi ringan
  − CannibalizationPenalty               ← 0 s.d. max_penalty (default 15)
```

Bobot (`w_demand`, `w_compete`) dan semua parameter berasal dari `franchise_categories.scoring_weights` — **tidak ada angka hard-code di kode**. Semua sub-faktor dinormalisasi ke persentil 0–100 terhadap distribusi baseline kota pilot.

**Verdict bands** (jangan tampilkan presisi palsu — band lebih penting dari angka):

| Skor | Verdict | Warna UI |
|---|---|---|
| ≥ 80 | `prime` | green |
| 65–79 | `strong` | teal |
| 50–64 | `conditional` | amber |
| < 50 | `avoid` | red |

---

## 2. Normalisasi Persentil

Semua nilai mentah dikonversi ke persentil terhadap **baseline kota**:

- **Baseline demografi**: distribusi nilai semua kelurahan di kota pilot.
- **Baseline kompetisi & anchor**: distribusi nilai semua sel `score_grid_cells` kategori tsb (dihitung saat precompute, disimpan sorted array in-memory / di-cache).

```python
def percentile(value: float, sorted_baseline: list[float]) -> float:
    """0-100. bisect di atas array sorted; baseline statis karena snapshot."""
    idx = bisect.bisect_left(sorted_baseline, value)
    return 100.0 * idx / len(sorted_baseline)
```

Alasan: "8 kompetitor dalam 1 km" tidak bermakna absolut — di Sudirman itu sepi, di area residensial itu jenuh. Persentil membuat skor comparable antar-lokasi dan self-calibrating saat pindah kota pilot.

---

## 3. Demand Index

`DemandIndex = Σ (weight_f × factor_score_f)` untuk 4 faktor:

### 3.1 `population_density`
Persentil `demographics.density_per_km2` kelurahan lokasi (point-in-polygon) terhadap semua kelurahan kota.

### 3.2 `demographic_match`
Cosine-like match antara struktur usia kelurahan dan profil target kategori:

```python
def demographic_match(age_dist: dict, target_weights: dict) -> float:
    """Σ (proporsi_usia × bobot_target), dinormalisasi ke 0-100
    terhadap match maksimum teoretis (semua penduduk di bucket bobot tertinggi)."""
    raw = sum(age_dist[k] * target_weights.get(k, 0) for k in age_dist)
    max_raw = max(target_weights.values())
    return 100.0 * raw / max_raw
```

### 3.3 `purchasing_power`
Persentil `purchasing_power_index` kelurahan. Jika `is_modeled=true`, faktor tetap dihitung tapi flag `is_modeled` diteruskan ke breakdown (UI menampilkan label) dan **confidence turun** (lihat §6).

### 3.4 `anchor_poi`
Skor gravitasi anchor dalam radius, dengan distance decay dan bobot per tipe anchor:

```python
def anchor_score(location, radius_m, tau_m, anchor_weights) -> float:
    anchors = query_places(location, radius_m, place_type='anchor')
    raw = sum(
        anchor_weights[a.anchor_type] * math.exp(-a.distance_m / tau_m)
        for a in anchors
    )
    return percentile(raw, baseline['anchor_raw'])   # baseline dari grid precompute
```

---

## 4. Competition Index

Dihitung sebagai **tekanan kompetitif** lalu **di-invert** (skor tinggi = kompetisi ringan) supaya semua pilar searah (tinggi = bagus).

### 4.1 `weighted_density` (bobot terbesar)
Jumlah kompetitor efektif dengan distance decay + bobot brand:

```python
def competitive_pressure(location, radius_m, category) -> float:
    comps = query_competitors(location, radius_m, category.id)
    return sum(
        (1.5 if c.is_chain else 1.0) * math.exp(-c.distance_m / category.decay_tau_m)
        for c in comps
    )

weighted_density_score = 100 - percentile(pressure, baseline['pressure'])
```

Kompetitor di 200 m ≈ bobot 0.72 (τ=600), di 2 km ≈ 0.04 — yang jauh nyaris tidak dihitung. Chain besar (`is_chain`) dihitung 1.5× karena daya saingnya lebih tinggi.

### 4.2 `per_capita_intensity`
`jumlah_kompetitor_dalam_radius ÷ populasi_kelurahan` → persentil → inverted. Menangkap kejenuhan relatif terhadap ukuran pasar.

### 4.3 `nearest_distance`
Jarak ke kompetitor terdekat → persentil langsung (makin jauh makin tinggi). Penting untuk kategori convenience (minimarket) di mana head-to-head adjacency mematikan.

```
CompetitionIndex = Σ (weight_f × factor_score_f)   # ketiganya sudah searah tinggi=bagus
```

---

## 5. Cannibalization Penalty

Hanya aktif jika `user_outlets` tidak kosong. Decay sendiri (`cannibalization.tau_m`, default 1200 m — trade area sendiri lebih luas dari radius kompetitor):

```python
def cannibalization_penalty(location, config) -> tuple[float, list]:
    outlets = query_user_outlets_within(location, radius_m=3 * config.tau_m)
    overlap = sum(math.exp(-o.distance_m / config.tau_m) for o in outlets)
    # overlap 1.0 ≈ satu outlet sendiri persis di sebelah → penalty penuh
    penalty = min(config.max_penalty, config.max_penalty * overlap)
    affected = [
        {"outlet_id": o.id, "name": o.name, "distance_m": o.distance_m,
         "overlap_pct": round(100 * math.exp(-o.distance_m / config.tau_m))}
        for o in outlets if o.distance_m < 2.5 * config.tau_m
    ]
    return round(penalty, 2), affected
```

---

## 6. Confidence Score

Kejujuran > presisi. Confidence 0–1 dari kelengkapan data, dikirim ke UI:

```python
def confidence(ctx) -> float:
    score = 1.0
    if ctx.demographics is None:            score -= 0.40   # fallback ke rata-rata kota
    elif ctx.demographics.is_modeled_pp:    score -= 0.10
    if ctx.snapshot_age_days > 180:         score -= 0.15
    if ctx.competitor_count == 0:           score -= 0.15   # area tanpa data ≠ area tanpa kompetitor
    if ctx.region_level == 'district':      score -= 0.10   # data kecamatan, bukan kelurahan
    return max(0.3, round(score, 2))
```

---

## 7. Pipeline Lengkap (Pseudocode)

```python
def analyze(lat, lng, category_slug, radius_m=None) -> AnalysisResult:
    cat = get_category(category_slug)
    radius = radius_m or cat.default_radius_m
    region = point_in_polygon(lat, lng)                    # kelurahan
    demo   = get_demographics(region)                      # + fallback district

    # pilar demand
    d1 = percentile(demo.density_per_km2, baseline_demo['density'])
    d2 = demographic_match(demo.age_distribution, cat.target_demo_profile['age_weights'])
    d3 = percentile(demo.purchasing_power_index, baseline_demo['pp'])
    d4 = anchor_score((lat,lng), radius, cat.decay_tau_m, cat.weights['anchor_type_weights'])
    demand = weighted_sum(cat.weights['demand_factors'], [d1,d2,d3,d4])

    # pilar competition
    c1 = 100 - percentile(competitive_pressure(...), baseline_grid['pressure'])
    c2 = 100 - percentile(count_in_radius / demo.population, baseline_grid['per_capita'])
    c3 = percentile(nearest_competitor_distance(...), baseline_grid['nearest'])
    competition = weighted_sum(cat.weights['competition_factors'], [c1,c2,c3])

    # komposit
    penalty, affected = cannibalization_penalty((lat,lng), cat.weights['cannibalization'])
    composite = clamp(
        cat.weights['pillars']['demand'] * demand +
        cat.weights['pillars']['competition'] * competition - penalty,
        0, 100)

    return AnalysisResult(
        composite=composite, demand=demand, competition=competition,
        penalty=penalty, verdict=to_verdict(composite),
        confidence=confidence(ctx),
        breakdown=build_breakdown(...))   # kontrak JSONB di database-schema.md §3.7
```

**Aturan breakdown**: setiap faktor WAJIB membawa `raw_value`, `percentile`, `weight`, `contribution` (± poin terhadap komposit), dan `evidence` (kalimat bahasa Indonesia siap tampil). `contribution` faktor demand = `pillar_weight × factor_weight × (factor_score − 50) / 50 × 50` — deviasi dari median, supaya UI bisa menampilkan "+12.9" / "−10.4" relatif terhadap lokasi netral.

---

## 8. Location Discovery (Grid Scan)

Reuse `analyze()` di atas grid precompute:

1. Job seed men-generate grid sel 250 m menutupi kota pilot (centroid per sel).
2. Untuk tiap sel × kategori: jalankan pipeline (tanpa cannibalization — itu per-user) → simpan ke `score_grid_cells`.
3. Endpoint discovery: filter `category_id` + `region_id` → return top-N sel + GeoJSON heatmap.
4. Klik sel di UI → jalankan `analyze()` penuh (dengan cannibalization) di centroid sel.

Kompleksitas: ±2.300 sel × 3 kategori, semua query lokal PostGIS → precompute penuh <1 menit, sekali jalan saat seed.

---

## 9. Transparansi & Batasan (wajib tampil di UI/dokumentasi)

1. Skor bersifat **relatif terhadap kota pilot**, bukan absolut antar kota.
2. `purchasing_power` adalah **modeled data** — bukan data BPS langsung.
3. Snapshot kompetitor bertanggal (`snapshot_date`) — dunia nyata bisa sudah berubah.
4. Skor 72 vs 74 = noise. Keputusan dibuat pada level verdict band.
5. Algoritma tidak memodelkan: harga sewa, visibilitas storefront, foot traffic aktual — semuanya Phase 2.
