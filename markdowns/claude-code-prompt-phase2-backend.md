# Prompt Claude Code — Phase 2 Backend (Wave 2A)

> Copy-paste dari root repo `localyze-be`. Prasyarat: MVP M1–M7 selesai, seed jalan, test hijau.

---

```
Kamu melanjutkan backend Localyze yang sudah jadi (FastAPI + PostGIS). Sekarang
implementasi Phase 2 Wave 2A: Disaster Risk, Economic Synergy, Export Memo PDF.

## LANGKAH PERTAMA (WAJIB)
1. Baca markdowns/phase2-backend-spec.md sampai selesai — skema, formula composite v2,
   kontrak breakdown.modifiers, API baru. Itu source of truth.
2. Baca ulang markdowns/scoring-algorithm.md §7 (pipeline) dan pahami implementasi
   existing di app/services/scoring.py + analyze.py sebelum mengubah apa pun.
3. Aturan lama tetap berlaku: parameter TIDAK hard-code (semua di DB/config),
   scoring pure functions, tanpa API eksternal runtime.

## URUTAN PENGERJAAN (commit per milestone)
P1. Migration 0002_phase2 (tabel disaster_risks + kolom synergy_map dengan preset
    3 kategori) + seed risks per kecamatan Jaksel (utamakan angka InaRISK publik;
    fallback modeled-v1 berlabel) + seed synergy_map. Seed tetap idempotent.
P2. Scoring v2: fungsi murni disaster_penalty() dan synergy_bonus() di
    services/scoring.py sesuai spec §2 + integrasi di analyze() + blok
    breakdown.modifiers persis kontrak spec + re-precompute score_grid_cells.
    Unit tests: penalty monotonic vs level; region tanpa data → 0 + flag +
    confidence turun; bonus capped max_bonus; composite clamp; analisis lama
    tanpa modifiers tetap valid di schema response.
P3. Endpoint: GET /regions/{id}/risks + GET /risks/choropleth?hazard=flood
    (GeoJSON kecamatan + level). Integration test keduanya.
P4. Memo PDF: pip install weasyprint jinja2 → app/templates/memo.html (layout 2
    halaman: verdict+skor+naratif+tabel faktor / kompetitor+demografi+risk+synergy+
    disclaimer) + build_narrative(breakdown) template-based deterministik (TANPA
    LLM) + POST /analyses/{id}/memo dan POST /analyses/compare/memo (auth, milik
    user sendiri saja). Test: response content-type application/pdf, >10KB,
    narasi non-kosong untuk 4 verdict.

## ACCEPTANCE
1. POST /analyses di titik Tebet → breakdown.modifiers.disaster & .synergy terisi,
   komposit berubah masuk akal vs sebelumnya (risiko banjir menurunkan, kantor
   di sekitar menaikkan).
2. GET /risks/choropleth?hazard=flood → GeoJSON semua kecamatan dengan level.
3. POST /analyses/{id}/memo → PDF terbuka, 2 halaman, Bahasa Indonesia, logo tampil.
4. GET /discovery → ranking berubah dibanding pre-Phase2 di kecamatan berisiko tinggi.
5. Semua test lama tetap hijau (regression).

Kerjakan P1 sekarang. Ringkas tiap milestone sebelum lanjut; kalau menemukan
konflik dengan kode existing, laporkan dulu jangan langsung refactor besar.
```
