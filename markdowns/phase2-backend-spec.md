# Localyze — Phase 2 Backend Spec (Wave 2A)

> **Status:** Phase 2 planning · **Created:** 2026-07-11 · **Owner:** Moym
> **Pasangan:** `../../localyze-fe/markdowns/phase2-feature-spec.md` (prioritisasi & UX).
> Scope dokumen ini: Wave 2A saja — Disaster Risk, Economic Synergy, Export Memo.

---

## 1. Perubahan Skema

### 1.1 `disaster_risks` (baru)

```sql
CREATE TABLE disaster_risks (
    id        SERIAL PRIMARY KEY,
    region_id INT NOT NULL REFERENCES regions(id),   -- level district (kecamatan)
    hazard    TEXT NOT NULL CHECK (hazard IN ('flood','earthquake','landslide')),
    level     SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 5),
    source    TEXT NOT NULL,          -- 'InaRISK 2025' | 'modeled-v1'
    data_year INT NOT NULL,
    UNIQUE (region_id, hazard)
);
```

Seed: per kecamatan Jaksel, 3 hazard. Utamakan angka dari InaRISK/BNPB publik; jika tidak sempat, sintetis-realistis dengan `source='modeled-v1'` (banjir tinggi di kecamatan dekat sungai — Pesanggrahan, Ciliwung; gempa seragam 2–3; longsor rendah 1–2).

### 1.2 `franchise_categories.synergy_map` (kolom JSONB baru)

```json
{
  "complementary": [
    { "match": {"anchor_type": "office"},  "weight": 1.0, "opportunity": "Partnership B2B / voucher karyawan" },
    { "match": {"anchor_type": "campus"},  "weight": 0.8, "opportunity": "Promo mahasiswa & event kampus" },
    { "match": {"anchor_type": "station"}, "weight": 0.6, "opportunity": "Grab-and-go komuter pagi" }
  ],
  "max_bonus": 5
}
```

Preset per kategori (kopi/laundry/minimarket) ditulis di seed — mapping lihat spec FE §2A.2.

---

## 2. Perubahan Scoring (composite v2)

```
composite = clamp( w_d·Demand + w_c·Competition − P_cannibal − P_disaster + B_synergy , 0, 100 )
```

- **P_disaster** (0..10): `max_over_hazards(level_norm × hazard_weight) × 10`, `level_norm = (level−1)/4`; `hazard_weight`: flood 1.0, earthquake 0.6, landslide 0.5. Kecamatan tanpa data → P=0 + flag `data_missing` (confidence −0.05).
- **B_synergy** (0..max_bonus): `min(max_bonus, Σ weight_i × exp(−d_i/τ))` di atas anchor/places komplementer dalam radius; τ pakai `decay_tau_m` kategori.
- Verdict bands tetap. `score_grid_cells` di-precompute ulang dengan P_disaster (synergy ikut? YA — keduanya deterministik per titik).

**Breakdown blok baru (kontrak FE):**

```json
"modifiers": {
  "disaster": {
    "penalty": 6.0,
    "hazards": [
      { "hazard": "flood", "level": 4, "evidence": "Risiko banjir level 4 (InaRISK 2025) — area langganan genangan",
        "mitigation": "Pertimbangkan unit lantai 2 atau asuransi banjir" },
      { "hazard": "earthquake", "level": 2, "evidence": "…", "mitigation": null }
    ],
    "source": "InaRISK 2025"
  },
  "synergy": {
    "bonus": 3.2,
    "opportunities": [
      { "type": "office", "count": 3, "nearest_m": 240, "weight_sum": 2.1,
        "evidence": "3 gedung kantor dalam 500 m",
        "opportunity": "Partnership B2B / voucher karyawan" }
    ]
  }
}
```

---

## 3. API Baru / Berubah

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| GET | `/regions/{id}/risks` | — | `[{hazard, level, source, data_year}]` |
| GET | `/risks/choropleth?hazard=flood` | — | GeoJSON kecamatan + properti `level` (untuk map layer) |
| POST | `/analyses/{id}/memo` | 🔒 | Generate PDF memo → `application/pdf`, filename `localyze-memo-{slug}.pdf` |
| POST | `/analyses/compare/memo?ids=a,b` | 🔒 | Memo perbandingan (≤3) |
| POST | `/analyses` | 🔒 | Response kini menyertakan `modifiers` di breakdown (backward compatible — blok baru, field lama tidak berubah) |

**Memo PDF:** render server-side pakai **WeasyPrint** (template HTML+CSS Jinja2 di `app/templates/memo.html`). Isi: h1 verdict + skor, ringkasan naratif template-based (fungsi `build_narrative(breakdown)` — kalimat dirakit dari evidence, deterministik, TANPA LLM), tabel faktor, kompetitor top-5, demografi, blok risk & synergy, disclaimer sumber data + `snapshot_date`. Logo dari file statis BE atau embed base64.

---

## 4. Konsistensi & Migrasi

- Alembic migration `0002_phase2`: tabel `disaster_risks`, kolom `synergy_map`, (nilai default untuk kategori existing), tambah kolom `modifiers` TIDAK perlu di `analyses` — sudah tertampung di JSONB `breakdown`.
- Analisis lama (tanpa `modifiers`) harus tetap terender di FE → FE guard `breakdown.modifiers?`.
- Seed idempotent: `python -m app.seed.run` menambahkan risks + synergy_map + re-precompute grid.
- Unit test wajib: P_disaster monotonic terhadap level; kecamatan tanpa data → 0 + flag; B_synergy capped di max_bonus; komposit ter-clamp; narasi memo menghasilkan string non-kosong untuk semua verdict.
