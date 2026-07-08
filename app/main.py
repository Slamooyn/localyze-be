from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health

app = FastAPI(title="Localyze API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(health.router)
# Additional routers (categories, regions, geocode, places, analyses, discovery,
# outlets) are registered here as each milestone lands.
app.include_router(api_v1)


@app.get("/")
def root() -> dict:
    return {"name": "Localyze API", "docs": "/docs", "api": "/api/v1"}
