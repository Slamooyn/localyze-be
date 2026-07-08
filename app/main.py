from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import SessionLocal
from app.routers import (
    analyses,
    categories,
    discovery,
    geocode,
    health,
    places,
    regions,
)
from app.services import baseline


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the percentile baselines from the seeded snapshot so the first request
    # is fast. Tolerate an empty/unseeded DB so the server still starts.
    db = SessionLocal()
    try:
        baseline.get(db)
    except Exception as exc:  # noqa: BLE001
        print(f"[startup] baseline warmup skipped: {exc}")
    finally:
        db.close()
    yield


app = FastAPI(title="Localyze API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix="/api/v1")
for r in (health, categories, regions, geocode, places, analyses, discovery):
    api_v1.include_router(r.router)
# outlets (M6) is registered as that milestone lands.
app.include_router(api_v1)


@app.get("/")
def root() -> dict:
    return {"name": "Localyze API", "docs": "/docs", "api": "/api/v1"}
