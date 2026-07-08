from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    lat: float
    lng: float
    category_slug: str
    radius_m: int | None = None
    include_cannibalization: bool = True
    name: str | None = None


class PatchAnalysisRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class LatLng(BaseModel):
    lat: float
    lng: float


class CategoryOut(BaseModel):
    id: int
    slug: str
    name: str
    default_radius_m: int
    decay_tau_m: int
    pillar_weights: dict


class RegionOut(BaseModel):
    id: int
    bps_code: str | None
    name: str
    level: str
    parent_id: int | None
