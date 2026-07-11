"""SQLAlchemy models — 1:1 with database-schema.md DDL."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from geoalchemy2 import Geography, Geometry
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FranchiseCategory(Base):
    __tablename__ = "franchise_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    google_place_types: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    decay_tau_m: Mapped[int] = mapped_column(Integer, nullable=False, server_default="800")
    default_radius_m: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1000")
    scoring_weights: Mapped[dict] = mapped_column(JSONB, nullable=False)
    target_demo_profile: Mapped[dict] = mapped_column(JSONB, nullable=False)
    synergy_map: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{\"complementary\": [], \"max_bonus\": 5}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("name", "category_id", name="uq_brand_name_cat"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("franchise_categories.id"))
    is_chain: Mapped[bool] = mapped_column(nullable=False, server_default="false")


class Region(Base):
    __tablename__ = "regions"
    __table_args__ = (
        CheckConstraint(
            "level IN ('city','district','subdistrict')", name="chk_region_level"
        ),
        Index("idx_regions_boundary", "boundary", postgresql_using="gist"),
        Index("idx_regions_parent", "parent_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bps_code: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    boundary = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True)
    centroid = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=True)


class Demographics(Base):
    __tablename__ = "demographics"

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id"), nullable=False, unique=True
    )
    population: Mapped[int] = mapped_column(Integer, nullable=False)
    density_per_km2: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    age_distribution: Mapped[dict] = mapped_column(JSONB, nullable=False)
    purchasing_power_index: Mapped[float | None] = mapped_column(Numeric(4, 2))
    is_modeled: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    data_year: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)


class DisasterRisk(Base):
    __tablename__ = "disaster_risks"
    __table_args__ = (
        CheckConstraint(
            "hazard IN ('flood','earthquake','landslide')", name="chk_hazard_enum"
        ),
        CheckConstraint("level BETWEEN 1 AND 5", name="chk_hazard_level"),
        UniqueConstraint("region_id", "hazard", name="uq_disaster_region_hazard"),
        Index("idx_disaster_region", "region_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id"), nullable=False
    )  # level district (kecamatan)
    hazard: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # 'InaRISK 2025' | 'modeled-v1'
    data_year: Mapped[int] = mapped_column(Integer, nullable=False)

    region: Mapped[Region] = relationship()


class Place(Base):
    __tablename__ = "places"
    __table_args__ = (
        CheckConstraint(
            "place_type IN ('competitor','anchor')", name="chk_place_type"
        ),
        CheckConstraint(
            "anchor_type IS NULL OR anchor_type IN "
            "('office','mall','campus','school','station','hospital')",
            name="chk_anchor_type_enum",
        ),
        CheckConstraint(
            "place_type <> 'competitor' OR category_id IS NOT NULL",
            name="chk_competitor_has_category",
        ),
        CheckConstraint(
            "place_type <> 'anchor' OR anchor_type IS NOT NULL",
            name="chk_anchor_has_type",
        ),
        Index("idx_places_location", "location", postgresql_using="gist"),
        Index(
            "idx_places_type_cat",
            "place_type",
            "category_id",
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    place_type: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("franchise_categories.id"))
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"))
    anchor_type: Mapped[str | None] = mapped_column(String)
    location = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=False)
    address: Mapped[str | None] = mapped_column(String)
    rating: Mapped[float | None] = mapped_column(Numeric(2, 1))
    rating_count: Mapped[int | None] = mapped_column(Integer)
    price_level: Mapped[int | None] = mapped_column(SmallInteger)
    source: Mapped[str] = mapped_column(String, nullable=False, server_default="seed")
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    brand: Mapped[Brand | None] = relationship()


class UserOutlet(Base):
    __tablename__ = "user_outlets"
    __table_args__ = (
        Index("idx_user_outlets_location", "location", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    location = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=False)
    address: Mapped[str | None] = mapped_column(String)
    import_batch: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('prime','strong','conditional','avoid')", name="chk_verdict"
        ),
        Index("idx_analyses_created", "created_at", postgresql_using="btree"),
        Index("idx_analyses_user", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("franchise_categories.id"), nullable=False
    )
    location = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=False)
    address: Mapped[str | None] = mapped_column(String)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False)
    score_composite: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    score_demand: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    score_competition: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    cannibalization_penalty: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default="0"
    )
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    category: Mapped[FranchiseCategory] = relationship()
    region: Mapped[Region | None] = relationship()


class ScoreGridCell(Base):
    __tablename__ = "score_grid_cells"
    __table_args__ = (
        UniqueConstraint("category_id", "geohash", name="uq_grid_cat_geohash"),
        Index("idx_grid_centroid", "centroid", postgresql_using="gist"),
        Index(
            "idx_grid_lookup",
            "category_id",
            "region_id",
            "score_composite",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("franchise_categories.id"), nullable=False
    )
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"))
    centroid = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=False)
    geohash: Mapped[str] = mapped_column(String, nullable=False)
    score_composite: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    score_demand: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    score_competition: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
