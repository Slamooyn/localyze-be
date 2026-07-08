# Localyze — Database Schema

> **Status:** MVP spec · **Created:** 2026-07-08 · **Owner:** Moym
> **Environment:** Local development (Docker Compose)
> **Stack:** PostgreSQL 16 + PostGIS 3.4 · SQLAlchemy 2 + GeoAlchemy2 · Alembic migrations

---

## 1. Prinsip Desain

1. **Snapshot-first, bukan live API.** Semua data kompetitor/POI adalah snapshot statis hasil satu kali tarik (Google Places API atau seed sintetis). Tidak ada live query ke API eksternal saat runtime — demo cepat, gratis, deterministik.
2. **Satu tabel `places` untuk kompetitor DAN anchor POI.** Keduanya berasal dari sumber yang sama (Places API), dibedakan lewat `place_type`. Anchor POI (kantor, mall, kampus, stasiun) adalah proxy demand gratis.
3. **Data demografi dilabeli jujur.** Kolom `is_modeled` membedakan data BPS asli vs estimasi. UI wajib menampilkan label "modeled data".
4. **Breakdown skor disimpan sebagai JSONB**, bukan tabel ternormalisasi — struktur breakdown akan sering berubah selama iterasi; JSONB fleksibel dan cukup untuk MVP.
5. **Geospatial pakai `geography(Point, 4326)`** untuk titik (jarak dalam meter langsung akurat) dan `geometry(MultiPolygon, 4326)` untuk wilayah admin.

---

## 2. ERD

```mermaid
erDiagram
    franchise_categories ||--o{ places : "categorizes competitors"
    franchise_categories ||--o{ analyses : "used by"
    franchise_categories ||--o{ score_grid_cells : "scored for"
    brands ||--o{ places : "owns"
    brands }o--|| franchise_categories : "belongs to"
    regions ||--o{ regions : "parent of"
    regions ||--|| demographics : "has"
    regions ||--o{ score_grid_cells : "contains"
    analyses }o--o| regions : "located in"
    user_outlets }o--|| brands : "belongs to"

    franchise_categories {
        int id PK
        text slug UK
        text name
        int decay_tau_m
        int default_radius_m
        jsonb scoring_weights
        jsonb target_demo_profile
    }
    brands {
        int id PK
        text name
        int category_id FK
        bool is_chain
    }
    regions {
        int id PK
        text bps_code UK
        text name
        text level
        int parent_id FK
        geometry boundary
        geography centroid
    }
    demographics {
        int id PK
        int region_id FK
        int population
        numeric density_per_km2
        jsonb age_distribution
        numeric purchasing_power_index
        bool is_modeled
        int data_year
        text source
    }
    places {
        bigint id PK
        text external_id UK
        text name
        text place_type
        int category_id FK
        int brand_id FK
        text anchor_type
        geography location
        text address
        numeric rating
        int rating_count
        smallint price_level
        date snapshot_date
        bool is_active
    }
    user_outlets {
        int id PK
        int brand_id FK
        text name
        geography location
        text address
        text import_batch
    }
    analyses {
        uuid id PK
        text name
        int category_id FK
        geography location
        text address
        int region_id FK
        int radius_m
        numeric score_composite
        numeric score_demand
        numeric score_competition
        numeric cannibalization_penalty
        text verdict
        numeric confidence
        jsonb breakdown
        timestamptz created_at
    }
    score_grid_cells {
        bigint id PK
        int category_id FK
        int region_id FK
        geography centroid
        text geohash
        numeric score_composite
        numeric score_demand
        numeric score_competition
        timestamptz computed_at
    }
```

---

## 3. Definisi Tabel (DDL)

### 3.1 `franchise_categories`

Kategori franchise + seluruh konfigurasi scoring per kategori. Menambah kategori baru = menambah baris, bukan menulis kode.

```sql
CREATE TABLE franchise_categories (
    id                SERIAL PRIMARY KEY,
    slug              TEXT NOT NULL UNIQUE,          -- 'coffee-grab-go', 'laundry', 'minimarket'
    name              TEXT NOT NULL,                 -- 'Kopi Grab-and-Go'
    google_place_types TEXT[] NOT NULL DEFAULT '{}', -- mapping ke Places API types, mis. {'cafe','coffee_shop'}
    decay_tau_m       INT  NOT NULL DEFAULT 800,     -- τ distance decay (meter)
    default_radius_m  INT  NOT NULL DEFAULT 1000,    -- radius analisis default
    scoring_weights   JSONB NOT NULL,                -- lihat struktur di bawah
    target_demo_profile JSONB NOT NULL,              -- profil demografi ideal kategori
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Struktur `scoring_weights`** (semua bobot 0–1, per-pilar dijumlah = 1):

```json
{
  "pillars": { "demand": 0.55, "competition": 0.45 },
  "demand_factors": {
    "population_density": 0.30,
    "demographic_match": 0.25,
    "purchasing_power": 0.20,
    "anchor_poi": 0.25
  },
  "competition_factors": {
    "weighted_density": 0.50,
    "per_capita_intensity": 0.30,
    "nearest_distance": 0.20
  },
  "anchor_type_weights": {
    "office": 1.0, "mall": 0.9, "campus": 0.8,
    "station": 0.7, "school": 0.5, "hospital": 0.4
  },
  "cannibalization": { "max_penalty": 15, "tau_m": 1200 }
}
```

**Struktur `target_demo_profile`:**

```json
{
  "age_weights": { "15_24": 0.35, "25_34": 0.35, "35_54": 0.20, "55_plus": 0.10 },
  "min_purchasing_power_index": 0.9
}
```

**Seed presets (3 kategori MVP):**

| slug | τ (m) | radius | demand : competition | Catatan kalibrasi |
|---|---|---|---|---|
| `coffee-grab-go` | 600 | 1000 | 0.55 : 0.45 | anchor_poi weight naik ke 0.35; office/campus dominan |
| `laundry` | 1000 | 1500 | 0.70 : 0.30 | population_density 0.45; kompetisi kurang relevan |
| `minimarket` | 500 | 800 | 0.50 : 0.50 | nearest_distance weight naik ke 0.40 |

### 3.2 `brands`

```sql
CREATE TABLE brands (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    category_id INT REFERENCES franchise_categories(id),
    is_chain    BOOLEAN NOT NULL DEFAULT false,   -- chain besar diberi bobot kompetitif lebih tinggi
    UNIQUE (name, category_id)
);
```

### 3.3 `regions`

Hirarki wilayah admin: city → district (kecamatan) → subdistrict (kelurahan). Pilot: Jakarta Selatan (atau kota pilot lain di Jabodetabek).

```sql
CREATE TABLE regions (
    id        SERIAL PRIMARY KEY,
    bps_code  TEXT UNIQUE,                          -- kode BPS, mis. '3171060'
    name      TEXT NOT NULL,
    level     TEXT NOT NULL CHECK (level IN ('city','district','subdistrict')),
    parent_id INT REFERENCES regions(id),
    boundary  geometry(MultiPolygon, 4326),
    centroid  geography(Point, 4326)
);

CREATE INDEX idx_regions_boundary ON regions USING GIST (boundary);
CREATE INDEX idx_regions_parent   ON regions (parent_id);
```

### 3.4 `demographics`

Satu baris per region (level `subdistrict` diutamakan; fallback ke `district` jika data kelurahan tidak ada).

```sql
CREATE TABLE demographics (
    id                      SERIAL PRIMARY KEY,
    region_id               INT NOT NULL UNIQUE REFERENCES regions(id),
    population              INT NOT NULL,
    density_per_km2         NUMERIC(10,2) NOT NULL,
    age_distribution        JSONB NOT NULL,          -- {"0_14":0.22,"15_24":0.18,"25_34":0.20,"35_54":0.26,"55_plus":0.14}
    purchasing_power_index  NUMERIC(4,2),            -- 1.00 = rata-rata kota; NULL jika tidak tersedia
    is_modeled              BOOLEAN NOT NULL DEFAULT false,
    data_year               INT NOT NULL,
    source                  TEXT NOT NULL             -- 'BPS 2024' | 'modeled-v1'
);
```

### 3.5 `places` — kompetitor & anchor POI

```sql
CREATE TABLE places (
    id            BIGSERIAL PRIMARY KEY,
    external_id   TEXT UNIQUE,                       -- Google place_id; NULL untuk data sintetis
    name          TEXT NOT NULL,
    place_type    TEXT NOT NULL CHECK (place_type IN ('competitor','anchor')),
    category_id   INT REFERENCES franchise_categories(id),  -- wajib untuk competitor, NULL untuk anchor
    brand_id      INT REFERENCES brands(id),
    anchor_type   TEXT CHECK (anchor_type IN ('office','mall','campus','school','station','hospital')),
    location      geography(Point, 4326) NOT NULL,
    address       TEXT,
    rating        NUMERIC(2,1),
    rating_count  INT,
    price_level   SMALLINT,                          -- 0-4 (skala Google)
    source        TEXT NOT NULL DEFAULT 'seed',      -- 'google-places' | 'seed' | 'manual'
    snapshot_date DATE NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT chk_competitor_has_category
        CHECK (place_type <> 'competitor' OR category_id IS NOT NULL),
    CONSTRAINT chk_anchor_has_type
        CHECK (place_type <> 'anchor' OR anchor_type IS NOT NULL)
);

CREATE INDEX idx_places_location ON places USING GIST (location);
CREATE INDEX idx_places_type_cat ON places (place_type, category_id) WHERE is_active;
```

### 3.6 `user_outlets` — untuk cannibalization guard

Outlet existing milik user (di-import via CSV). MVP tanpa auth: cukup satu namespace global + `import_batch` untuk membedakan sesi import.

```sql
CREATE TABLE user_outlets (
    id           SERIAL PRIMARY KEY,
    brand_id     INT REFERENCES brands(id),
    name         TEXT NOT NULL,
    location     geography(Point, 4326) NOT NULL,
    address      TEXT,
    import_batch TEXT NOT NULL,                      -- uuid per upload CSV
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_outlets_location ON user_outlets USING GIST (location);
```

**Format CSV import:** `name,lat,lng,address` (header wajib, delimiter koma).

### 3.7 `analyses` — hasil analisis tersimpan

```sql
CREATE TABLE analyses (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT,                    -- editable, default = alamat
    category_id             INT NOT NULL REFERENCES franchise_categories(id),
    location                geography(Point, 4326) NOT NULL,
    address                 TEXT,
    region_id               INT REFERENCES regions(id),   -- kelurahan hasil point-in-polygon
    radius_m                INT NOT NULL,
    score_composite         NUMERIC(5,2) NOT NULL,   -- 0-100
    score_demand            NUMERIC(5,2) NOT NULL,
    score_competition       NUMERIC(5,2) NOT NULL,   -- sudah inverted (tinggi = kompetisi ringan)
    cannibalization_penalty NUMERIC(5,2) NOT NULL DEFAULT 0,
    verdict                 TEXT NOT NULL CHECK (verdict IN ('prime','strong','conditional','avoid')),
    confidence              NUMERIC(3,2) NOT NULL,   -- 0-1, dari kelengkapan data
    breakdown               JSONB NOT NULL,          -- struktur di bawah
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_analyses_created ON analyses (created_at DESC);
```

**Struktur `breakdown`** — kontrak eksplisit dengan FE (setiap faktor = kontribusi ±poin + bukti):

```json
{
  "demand": {
    "score": 68.4,
    "factors": [
      {
        "key": "population_density",
        "label": "Kepadatan penduduk",
        "raw_value": 15234, "unit": "jiwa/km²",
        "percentile": 78, "weight": 0.30,
        "contribution": 12.9,
        "evidence": "15.234 jiwa/km² — persentil ke-78 se-Jakarta Selatan"
      },
      { "key": "demographic_match", "...": "..." },
      { "key": "purchasing_power", "is_modeled": true, "...": "..." },
      { "key": "anchor_poi", "...": "..." }
    ]
  },
  "competition": {
    "score": 41.2,
    "factors": [
      {
        "key": "weighted_density",
        "raw_value": 8, "unit": "kompetitor efektif dlm radius",
        "percentile": 85, "weight": 0.50,
        "contribution": -10.4,
        "evidence": "8 kompetitor dalam 1 km (persentil ke-85 terpadat)"
      },
      { "key": "per_capita_intensity", "...": "..." },
      { "key": "nearest_distance", "...": "..." }
    ],
    "competitors_in_radius": [
      { "place_id": 123, "name": "Kopi X Tebet", "distance_m": 210, "decay_weight": 0.70, "is_chain": true }
    ]
  },
  "cannibalization": {
    "penalty": 4.5,
    "affected_outlets": [ { "outlet_id": 3, "name": "Outlet Tebet", "distance_m": 850, "overlap_pct": 22 } ]
  },
  "data_completeness": {
    "demographics_available": true, "purchasing_power_modeled": true,
    "competitor_snapshot_date": "2026-07-01"
  }
}
```

### 3.8 `score_grid_cells` — precompute untuk Location Discovery

Grid heksagonal/persegi ~250 m yang menutupi wilayah pilot, di-precompute per kategori oleh job seed (bukan on-the-fly).

```sql
CREATE TABLE score_grid_cells (
    id                BIGSERIAL PRIMARY KEY,
    category_id       INT NOT NULL REFERENCES franchise_categories(id),
    region_id         INT REFERENCES regions(id),    -- kecamatan induk sel
    centroid          geography(Point, 4326) NOT NULL,
    geohash           TEXT NOT NULL,                 -- presisi 7 (~150m) untuk dedup/join cepat
    score_composite   NUMERIC(5,2) NOT NULL,
    score_demand      NUMERIC(5,2) NOT NULL,
    score_competition NUMERIC(5,2) NOT NULL,
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (category_id, geohash)
);

CREATE INDEX idx_grid_centroid ON score_grid_cells USING GIST (centroid);
CREATE INDEX idx_grid_lookup   ON score_grid_cells (category_id, region_id, score_composite DESC);
```

> Estimasi ukuran: Jakarta Selatan ±145 km² ÷ (0.25 km)² ≈ 2.300 sel × 3 kategori ≈ 7.000 baris. Precompute penuh <1 menit di laptop.

---

## 4. Query Geospatial Kunci

**Kompetitor dalam radius (dengan jarak):**

```sql
SELECT p.id, p.name, b.is_chain,
       ST_Distance(p.location, ST_MakePoint(:lng, :lat)::geography) AS distance_m
FROM places p
LEFT JOIN brands b ON b.id = p.brand_id
WHERE p.place_type = 'competitor'
  AND p.category_id = :category_id
  AND p.is_active
  AND ST_DWithin(p.location, ST_MakePoint(:lng, :lat)::geography, :radius_m)
ORDER BY distance_m;
```

**Point-in-polygon (lokasi → kelurahan):**

```sql
SELECT id, name FROM regions
WHERE level = 'subdistrict'
  AND ST_Contains(boundary, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326))
LIMIT 1;
```

**Persentil baseline kota** — dihitung sekali saat seed, di-cache di memori aplikasi (distribusi statis karena snapshot): simpan array sorted nilai per faktor per kategori, lookup persentil via bisect. Tidak perlu tabel tambahan.

---

## 5. Strategi Seed Data (Local Dev)

Urutan seed (idempotent, jalankan via `python -m app.seed`):

1. **`regions`** — GeoJSON batas kecamatan+kelurahan Jakarta Selatan (sumber: GADM/BPS open data, file disimpan di `seed/data/regions.geojson`).
2. **`demographics`** — CSV kepadatan & struktur usia per kelurahan (BPS). Purchasing power di-generate modeled (`is_modeled=true`) dari proxy harga sewa area.
3. **`franchise_categories` + `brands`** — 3 kategori preset + ±15 brand kompetitor realistis per kategori (Kopi Kenangan, Fore, Janji Jiwa, dst. untuk coffee).
4. **`places`** — dua mode:
   - `SEED_MODE=synthetic` (default): generator sintetis-realistis — kompetitor terklaster di koridor komersial (didefinisikan sebagai polyline di seed config), anchor POI di titik nyata yang di-hardcode (±80 titik: mall, stasiun MRT, kampus, gedung kantor Jaksel).
   - `SEED_MODE=google` (opsional): script tarik Google Places API sekali → simpan ke JSON → load. API key via env, hasil JSON di-commit supaya rekan tim tidak perlu key.
5. **`score_grid_cells`** — precompute grid setelah semua data masuk.

**Target volume seed:** ±400 kompetitor + ±80 anchor untuk Jaksel — cukup padat untuk demo yang meyakinkan.

---

## 6. Docker Compose (Local)

```yaml
services:
  db:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: localyze
      POSTGRES_USER: localyze
      POSTGRES_PASSWORD: localyze
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
volumes:
  pgdata:
```

Connection string local: `postgresql+psycopg://localyze:localyze@localhost:5432/localyze`

---

## 7. Out of Scope (MVP)

- Tabel `users`/auth — MVP single-tenant local.
- Time-series kompetitor (saturation velocity) — butuh snapshot berkala, Phase 2.
- Tabel disaster risk & economic lifecycle — Phase 2 (ditampilkan sebagai teaser di UI).
- Materialized views — volume data snapshot terlalu kecil untuk membutuhkannya.
