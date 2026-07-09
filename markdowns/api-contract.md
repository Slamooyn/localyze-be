# Localyze — API Contract (MVP)

> **Status:** MVP spec · **Created:** 2026-07-08 · **Owner:** Moym
> **Stack:** FastAPI · base URL local: `http://localhost:8000/api/v1`
> **Prasyarat:** `database-schema.md`, `scoring-algorithm.md`

Konvensi: JSON snake_case · error format `{"detail": {"code": "...", "message": "..."}}` · semua koordinat `{lat, lng}` WGS84 · CORS allow `http://localhost:3000`.

**Auth:** JWT bearer (`Authorization: Bearer <token>`). Endpoint **`/analyses*` dan `/outlets*` wajib auth** (data milik user); endpoint referensi/geospatial (`/categories`, `/regions*`, `/geocode*`, `/places`, `/discovery`, `/health`) publik. `401 {"code":"UNAUTHORIZED"}` bila token tidak ada/invalid/expired.

---

## 0. Auth

### `POST /auth/register`
Request: `{"name": "Moym", "email": "moym@mail.com", "password": "min8chars"}`
Response `201`:

```json
{
  "token": "eyJ…",
  "user": { "id": "uuid", "name": "Moym", "email": "moym@mail.com" }
}
```

Error `409 {"code":"EMAIL_TAKEN"}` · `422` validasi (password <8, email invalid).

### `POST /auth/login`
Request: `{"email": "...", "password": "..."}` → `200` payload sama dengan register.
Error `401 {"code":"INVALID_CREDENTIALS"}` (pesan sama untuk email tak terdaftar vs password salah).

### `GET /auth/me` 🔒
`200 {"id","name","email","created_at"}` — dipakai FE untuk topbar/user menu.

Detail token: HS256, `sub` = user id, expiry 7 hari (demo build), secret via env `JWT_SECRET`.
Akun demo tersedia dari seed: `demo@localyze.id` / `demo1234`.

---

## 1. Meta & Referensi

### `GET /health`
`200 {"status":"ok","db":"ok","seed_version":"2026-07-01"}`

### `GET /categories`
Daftar kategori franchise + konfigurasi yang relevan untuk UI.

```json
[
  {
    "id": 1, "slug": "coffee-grab-go", "name": "Kopi Grab-and-Go",
    "default_radius_m": 1000, "decay_tau_m": 600,
    "pillar_weights": { "demand": 0.55, "competition": 0.45 }
  }
]
```

### `GET /regions?level=district`
Daftar wilayah untuk dropdown Discovery. `{id, bps_code, name, level, parent_id}`.

### `GET /regions/{id}/demographics`
Detail demografi satu wilayah (untuk demographic profile card).

```json
{
  "region": { "id": 42, "name": "Tebet", "level": "subdistrict" },
  "population": 23400, "density_per_km2": 15234.5,
  "age_distribution": { "0_14": 0.22, "15_24": 0.18, "25_34": 0.20, "35_54": 0.26, "55_plus": 0.14 },
  "purchasing_power_index": 1.12, "is_modeled": true,
  "data_year": 2024, "source": "BPS 2024 + modeled-v1"
}
```

---

## 2. Geocoding (Local)

### `GET /geocode?q=tebet`
Search-as-you-type di atas data lokal (nama kelurahan/kecamatan + nama `places`). **Bukan** proxy ke API eksternal.

```json
[ { "label": "Tebet, Jakarta Selatan", "lat": -6.2264, "lng": 106.8531, "type": "region", "region_id": 42 } ]
```

### `GET /reverse-geocode?lat=-6.2264&lng=106.8531`
Point-in-polygon → `{region_id, name, level, address_approx}`. Dipakai saat user klik peta.

---

## 3. Places

### `GET /places?lat&lng&radius_m&category_id&place_type=competitor|anchor`
Untuk map overlay. Response GeoJSON `FeatureCollection`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [106.8531, -6.2264] },
      "properties": {
        "id": 123, "name": "Kopi X Tebet", "place_type": "competitor",
        "brand": "Kopi X", "is_chain": true, "rating": 4.5,
        "distance_m": 210, "anchor_type": null
      }
    }
  ]
}
```

---

## 4. Analysis (inti produk) 🔒

Semua endpoint di bagian ini wajib bearer token; setiap analisis tersimpan milik user pembuatnya, dan list/get/compare hanya mengembalikan milik user tsb (lainnya → `404`).

### `POST /analyses`

Request:

```json
{
  "lat": -6.2264, "lng": 106.8531,
  "category_slug": "coffee-grab-go",
  "radius_m": 1000,
  "include_cannibalization": true,
  "name": null
}
```

Response `201` — **satu payload lengkap untuk seluruh score panel** (FE tidak perlu request tambahan):

```json
{
  "id": "6f1c…", "name": "Tebet, Jakarta Selatan",
  "location": { "lat": -6.2264, "lng": 106.8531 },
  "region": { "id": 42, "name": "Tebet" },
  "category": { "slug": "coffee-grab-go", "name": "Kopi Grab-and-Go" },
  "radius_m": 1000,
  "score": {
    "composite": 72.3, "demand": 68.4, "competition": 41.2,
    "cannibalization_penalty": 4.5,
    "verdict": "strong", "confidence": 0.85
  },
  "breakdown": { "…": "kontrak persis database-schema.md §3.7" },
  "created_at": "2026-07-08T10:00:00Z"
}
```

Error: `422` koordinat di luar coverage → `{"code":"OUT_OF_COVERAGE","message":"Lokasi di luar wilayah pilot (Jakarta Selatan)"}`.

### `GET /analyses` — riwayat, `?limit=20&offset=0`, sorted terbaru.
### `GET /analyses/{id}` — payload sama dengan POST.
### `PATCH /analyses/{id}` — `{"name": "Kandidat Tebet Raya"}`.
### `DELETE /analyses/{id}` — `204`.

### `GET /analyses/compare?ids=uuid1,uuid2,uuid3`
Maks 3. Response array payload analisis penuh + blok delta:

```json
{
  "analyses": [ "…payload penuh…" ],
  "deltas": {
    "best_composite": "uuid1",
    "factor_winners": { "population_density": "uuid2", "anchor_poi": "uuid1", "weighted_density": "uuid1" }
  }
}
```

---

## 5. Location Discovery

### `GET /discovery?category_slug=coffee-grab-go&region_id=7&limit=10`
`region_id` = kecamatan (level `district`). Response: ranked list + heatmap dalam satu payload:

```json
{
  "top_locations": [
    {
      "rank": 1, "cell_id": 9812,
      "centroid": { "lat": -6.2401, "lng": 106.8302 },
      "region_name": "Kebayoran Baru",
      "score_composite": 84.1, "score_demand": 82.0, "score_competition": 71.5,
      "verdict": "prime"
    }
  ],
  "heatmap": {
    "type": "FeatureCollection",
    "features": [ { "geometry": { "type": "Point", "coordinates": [106.8302, -6.2401] },
                    "properties": { "score": 84.1 } } ]
  },
  "computed_at": "2026-07-01T00:00:00Z"
}
```

Interaksi lanjutan: user klik sel → FE panggil `POST /analyses` di centroid tsb (dapat breakdown penuh + cannibalization).

---

## 6. User Outlets (Cannibalization Guard) 🔒

Wajib bearer token — outlet ter-scope per user; cannibalization di `POST /analyses` hanya menghitung outlet milik user yang sedang login.

### `POST /outlets/import` — multipart CSV
CSV header wajib: `name,lat,lng,address`. Response:

```json
{ "import_batch": "b7e2…", "imported": 12, "skipped": [ { "row": 4, "reason": "invalid lat" } ] }
```

### `GET /outlets` — semua outlet aktif (GeoJSON, untuk layer peta).
### `DELETE /outlets?import_batch=b7e2…` — hapus satu batch; tanpa param = hapus semua.

---

## 7. Ringkasan Endpoint

| Method | Path | Auth | Fungsi |
|---|---|---|---|
| POST | `/auth/register` · `/auth/login` | — | daftar & masuk (JWT) |
| GET | `/auth/me` | 🔒 | profil user login |
| GET | `/health` | — | health check |
| GET | `/categories` | — | daftar kategori + config |
| GET | `/regions` | — | daftar wilayah |
| GET | `/regions/{id}/demographics` | — | profil demografi |
| GET | `/geocode` · `/reverse-geocode` | — | pencarian lokal |
| GET | `/places` | — | overlay kompetitor/anchor (GeoJSON) |
| POST/GET/PATCH/DELETE | `/analyses…` | 🔒 | analisis & riwayat (per user) |
| GET | `/analyses/compare` | 🔒 | perbandingan ≤3 lokasi |
| GET | `/discovery` | — | grid scan top-N + heatmap |
| POST/GET/DELETE | `/outlets…` | 🔒 | import & kelola outlet sendiri (per user) |
