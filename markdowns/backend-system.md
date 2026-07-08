# Localyze Backend — Index Dokumentasi

> Diperbarui: 2026-07-08

Urutan baca untuk memahami sistem:

0. **`tech-stack-backend.md`** — decision record framework: FastAPI + PostGIS (kenapa, dan alternatif yang ditolak).
1. **`database-schema.md`** — skema data lengkap: ERD, DDL 8 tabel (PostGIS), strategi seed data lokal (synthetic + snapshot Google Places opsional), docker-compose.
2. **`scoring-algorithm.md`** — formula Localyze Score: distance decay, normalisasi persentil, demand & competition index, cannibalization penalty, confidence, grid scan Discovery.
3. **`api-contract.md`** — kontrak seluruh endpoint `/api/v1` (request/response shapes, dipakai FE sebagai source of truth types).
4. **`claude-code-prompt-backend.md`** — prompt siap jalan di Claude Code untuk implementasi (milestone M1–M6 + acceptance criteria).

Keputusan arsitektur kunci: snapshot-first (tanpa API eksternal saat runtime), semua parameter scoring di tabel `franchise_categories` (bukan hard-code), local dev penuh via Docker Compose.
