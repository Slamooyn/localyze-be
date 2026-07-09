# Localyze Backend

FastAPI + PostgreSQL/PostGIS location-intelligence API for franchise site scoring.
Fully local — **no external API calls at runtime**, all data comes from a synthetic
Jakarta Selatan snapshot.

## Run from zero (6 commands)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d           # Postgres+PostGIS on host port 5433
alembic upgrade head           # create the 8 tables + PostGIS
python -m app.seed.run         # seed regions/demographics/places + precompute grid
uvicorn app.main:app --reload  # http://localhost:8000  (docs at /docs)
```

Quick check:

```bash
curl localhost:8000/api/v1/health
curl "localhost:8000/api/v1/categories"
curl -X POST localhost:8000/api/v1/analyses -H 'Content-Type: application/json' \
  -d '{"lat":-6.2264,"lng":106.8531,"category_slug":"coffee-grab-go"}'
```

## Auth

`/analyses*` and `/outlets*` require a JWT bearer token; reference/geospatial endpoints
are public. Register/login return `{token, user}`.

```bash
# demo account (seeded): 2 sample analyses + 3 outlets
curl -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"demo@localyze.id","password":"demo1234"}'
```

Token: HS256, `sub`=user id, 7-day expiry, secret via `JWT_SECRET` env.

## Notes / deviations from spec

- **Sync SQLAlchemy 2.0 + psycopg3** instead of async. `tech-stack-backend.md` §1.5
  calls async a *bonus, not a requirement*; sync keeps Alembic, the seed scripts, and
  baseline computation simpler and more reliable. FastAPI sync endpoints run in a
  threadpool.
- **argon2-cffi** for password hashing instead of `passlib[argon2]` — passlib is
  unmaintained and breaks on Python 3.12+ (`crypt` module removed); argon2-cffi is the
  same argon2 backend passlib wraps, used directly.
- **Postgres is mapped to host port `5433`** (not 5432) to avoid clashing with a
  Postgres already running on the host. Connection string in `.env`.
- **Regions/demographics are generated deterministically** (a 5×2 kecamatan grid over
  a Jaksel bounding box, each split into 4 kelurahan = 40 subdistricts). Anchors are
  curated real Jaksel coordinates (`app/seed/data/anchors.json`); competitors are
  clustered along commercial corridors. Everything is seeded (fixed RNG) so every run
  is identical.

## Layout

```
app/
  main.py            FastAPI app + CORS + baseline warmup (lifespan)
  models/            SQLAlchemy models (1:1 with database-schema.md)
  schemas/           Pydantic request/response models
  routers/           health, categories, regions, geocode, places, analyses, discovery, outlets
  services/
    scoring.py       PURE scoring functions (unit-tested, no I/O)
    geo.py           PostGIS queries
    baseline.py      percentile baselines (sampled once, cached)
    analyze.py       orchestrator: geo + baseline + scoring -> full breakdown
    geohash.py       minimal geohash encoder
  seed/              synthetic Jaksel data + grid precompute
alembic/             migrations
tests/               unit (scoring) + integration (endpoints)
```

## Tests & lint

```bash
pytest        # 19 tests: pure scoring unit tests + endpoint integration tests
ruff check app tests
```

## Endpoints (`/api/v1`)

`GET /health` · `GET /categories` · `GET /regions` · `GET /regions/{id}/demographics` ·
`GET /geocode` · `GET /reverse-geocode` · `GET /places` ·
`POST|GET|PATCH|DELETE /analyses…` · `GET /analyses/compare` · `GET /discovery` ·
`POST|GET|DELETE /outlets…`

See `markdowns/api-contract.md` for full request/response shapes.
