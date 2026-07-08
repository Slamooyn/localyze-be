# Localyze Backend — Rekomendasi Framework & Tech Stack

> **Status:** Decision record · **Created:** 2026-07-08 · **Owner:** Moym
> **Keputusan:** FastAPI (Python) + PostgreSQL/PostGIS

---

## 1. Rekomendasi: FastAPI

**FastAPI + SQLAlchemy 2 + GeoAlchemy2 + PostGIS** adalah pilihan terbaik untuk Localyze, dan sudah menjadi asumsi seluruh spec (`database-schema.md`, `api-contract.md`).

Alasan utama, diurutkan dari yang paling menentukan:

1. **Geospatial adalah inti produk, dan ekosistem Python + PostGIS adalah yang terkuat.** GeoAlchemy2 memetakan `geography/geometry` langsung ke ORM; Shapely/GeoPandas tersedia kalau seed pipeline butuh olah GeoJSON. Tidak ada ekosistem lain yang se-matang ini untuk kasus kita.
2. **Scoring engine = komputasi numerik.** Formula decay, persentil, weighted sum jauh lebih natural ditulis dan di-unit-test di Python (math/bisect/numpy bila perlu) daripada di Node/PHP.
3. **Pydantic v2 = kontrak API hidup.** Response model di kode identik dengan `api-contract.md`, tervalidasi otomatis, dan menghasilkan OpenAPI docs (`/docs`) gratis — FE bisa lihat shape API tanpa nanya.
4. **Ringan dan cepat di-scaffold.** Untuk MVP single-tenant tanpa auth, kita tidak butuh "baterai" Django (admin, auth, forms). FastAPI memulai kecil dan tidak menghukum kita untuk itu.
5. **Async native** — berguna saat grid precompute dan query paralel, meski di skala MVP ini bonus, bukan kebutuhan.

## 2. Alternatif yang Dipertimbangkan

| Framework | Kekuatan | Kenapa tidak dipilih |
|---|---|---|
| **Django + GeoDjango** | GeoDjango matang, admin panel gratis (enak untuk kelola seed data manual), ORM kuat | Lebih berat; admin tidak terlalu dibutuhkan karena data kita snapshot hasil script, bukan CRUD manual. Pilihan #2 yang sah — pilih ini kalau kamu lebih nyaman dengan struktur "batteries included" |
| **NestJS / Express (Node)** | Satu bahasa dengan FE (TypeScript), NestJS terstruktur rapi | Ekosistem geospatial (TypeORM + PostGIS) jauh lebih kasar; komputasi scoring & tooling numeriknya kalah; dua bahasa (TS+SQL mentah) untuk hal yang Python selesaikan native |
| **Laravel (PHP)** | Familiar di banyak kampus, Eloquent enak | Dukungan PostGIS pihak ketiga dan kurang terawat; scoring numerik & test tooling kurang cocok |
| **Go (Gin/Fiber)** | Performa | Overkill untuk MVP; development speed kalah jauh; geospatial lib minim |

**Aturan praktis:** kalau kamu sudah lancar Python → FastAPI (keputusan ini). Kalau kamu jauh lebih lancar TypeScript dan rela kerja ekstra di sisi geospatial → NestJS bisa, tapi seluruh spec BE harus diterjemahkan ulang. Rekomendasi saya tetap FastAPI.

## 3. Stack Lengkap (final)

| Layer | Pilihan | Catatan |
|---|---|---|
| Bahasa | Python 3.12 | |
| Framework | FastAPI | router modular per resource |
| ORM | SQLAlchemy 2 (async) + GeoAlchemy2 | |
| Validasi/serialisasi | Pydantic v2 | 1:1 dengan `api-contract.md` |
| Migrasi | Alembic | |
| Database | PostgreSQL 16 + PostGIS 3.4 | via Docker Compose (lihat `database-schema.md` §6) |
| Test | pytest + httpx | unit (scoring) + integration (endpoint) |
| Lint/format | ruff | |
| Runtime local | uvicorn --reload | port 8000 |

Tidak dipakai di MVP (sengaja): Redis/cache eksternal (baseline persentil cukup in-memory), Celery/worker (precompute jalan sebagai script seed), auth (single-tenant local).
