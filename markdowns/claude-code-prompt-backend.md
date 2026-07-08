# Prompt Claude Code — Localyze Backend

> Copy-paste prompt di bawah ini ke Claude Code, dijalankan dari root repo `localyze-be`.

---

```
Kamu adalah backend engineer untuk Localyze — Franchise Location Intelligence Platform.

## LANGKAH PERTAMA (WAJIB)
Baca ketiga spec ini sampai selesai sebelum menulis kode apa pun:
1. markdowns/database-schema.md   — skema data, DDL, seed strategy, docker-compose
2. markdowns/scoring-algorithm.md — formula scoring, pseudocode, kontrak breakdown
3. markdowns/api-contract.md      — seluruh endpoint, request/response shapes

Spec adalah source of truth. Jika ada ambiguitas, ikuti spec; jika spec diam, putuskan
sendiri dengan prinsip: sederhana > canggih, explainable > akurat.

## TECH STACK (fixed, jangan diganti)
- Python 3.12, FastAPI, SQLAlchemy 2 (async) + GeoAlchemy2, Alembic, Pydantic v2
- PostgreSQL 16 + PostGIS 3.4 via docker-compose (definisi di database-schema.md §6)
- pytest + httpx untuk test; ruff untuk lint
- TIDAK ADA panggilan API eksternal saat runtime — semua data dari seed lokal

## STRUKTUR PROJECT
app/
  main.py            — FastAPI app, CORS (allow http://localhost:3000), /api/v1 router
  config.py          — pydantic-settings, DATABASE_URL, SEED_MODE
  models/            — SQLAlchemy models (1:1 dengan DDL di spec)
  schemas/           — Pydantic response/request models (1:1 dengan api-contract.md)
  routers/           — health, categories, regions, geocode, places, analyses, discovery, outlets
  services/
    scoring.py       — implementasi PERSIS scoring-algorithm.md (pure functions, mudah di-unit-test)
    baseline.py      — percentile baselines, dihitung saat startup dari DB, cache in-memory
    geo.py           — query PostGIS (ST_DWithin, point-in-polygon)
  seed/
    run.py           — python -m app.seed.run, idempotent, urutan sesuai spec §5
    data/            — regions.geojson, demographics.csv, anchors.json, brands.json
    synthetic.py     — generator kompetitor sintetis-realistis (klaster di koridor komersial)
alembic/             — migrations
tests/

## URUTAN PENGERJAAN (commit per milestone)
M1. Scaffold + docker-compose + alembic migration pertama (semua tabel) + /health hijau
M2. Seed pipeline lengkap (SEED_MODE=synthetic): regions Jaksel, demographics,
    3 kategori preset (bobot dari spec §3.1), ±400 kompetitor + ±80 anchor.
    Anchor nyata Jaksel hard-code minimal 40 titik (mall, stasiun MRT, kampus, kantor).
M3. services/scoring.py + unit tests. Test wajib:
    - distance decay: kompetitor 200m berbobot > kompetitor 2km
    - persentil monotonic; nilai di luar baseline ter-clamp 0/100
    - verdict bands di boundary (79.99 → strong, 80.0 → prime)
    - cannibalization: 0 tanpa outlet; capped di max_penalty
    - breakdown: setiap faktor punya raw_value, percentile, weight, contribution, evidence
M4. Endpoints: geocode, reverse-geocode, places, analyses (CRUD + compare) — sesuai kontrak.
    Integration test happy path POST /analyses di koordinat Tebet (-6.2264, 106.8531)
    harus mengembalikan payload lengkap sesuai kontrak dengan verdict yang masuk akal.
M5. Grid precompute (score_grid_cells, sel 250m) sebagai step terakhir seed + GET /discovery.
M6. Endpoint outlets (CSV import dengan validasi per baris + laporan skipped).

## QUALITY BAR
- scoring.py: pure functions tanpa I/O — semua data via parameter. Ini yang di-unit-test.
- Angka bobot/τ/penalty TIDAK boleh hard-code di kode — semuanya dari franchise_categories.
- Response time POST /analyses < 500ms di data seed (profiling sederhana cukup).
- README.md: cara jalanin dari nol (docker compose up → alembic upgrade → seed → uvicorn)
  dalam ≤6 perintah.
- Setiap milestone: ruff clean + pytest hijau sebelum commit.

## DEMO ACCEPTANCE (cek manual di akhir)
1. curl POST /analyses di Tebet → verdict masuk akal, breakdown lengkap, evidence bahasa Indonesia.
2. curl GET /discovery kecamatan Kebayoran Baru → top-10 dengan skor bervariasi (bukan seragam).
3. Import CSV 3 outlet dekat Tebet → POST /analyses yang sama → composite turun karena penalty.

Kerjakan M1 sekarang. Setelah tiap milestone, ringkas apa yang selesai + apa yang berubah
dari spec (jika ada) sebelum lanjut.
```
