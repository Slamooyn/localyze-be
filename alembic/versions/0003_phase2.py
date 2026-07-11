"""phase 2 (wave 2A): disaster_risks table + franchise_categories.synergy_map

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-11

Spec: markdowns/phase2-backend-spec.md §1 (the spec names this "0002_phase2", but
revision 0002 is already taken by auth — kept as 0003, same content).

Written defensively: migration 0001 builds the schema from live model metadata, so a
FRESH database already has `disaster_risks` and the `synergy_map` column. This
migration only fills the gap on a database that was migrated under the v1/v2 models,
and backfills the synergy presets for existing category rows (fresh databases get
the presets from the seed).
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.reflection import Inspector

from app.db import Base
from app import models  # noqa: F401
from app.seed import config as seed_config

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMPTY_SYNERGY = '{"complementary": [], "max_bonus": 5}'


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)
    tables = set(insp.get_table_names())

    if "disaster_risks" not in tables:
        Base.metadata.tables["disaster_risks"].create(bind)

    cols = {c["name"] for c in insp.get_columns("franchise_categories")}
    if "synergy_map" not in cols:
        op.add_column(
            "franchise_categories",
            sa.Column(
                "synergy_map",
                JSONB,
                nullable=False,
                server_default=sa.text(f"'{EMPTY_SYNERGY}'::jsonb"),
            ),
        )
        # Backfill the category presets (seed config is the single source of the
        # parameter values — nothing hard-coded here).
        for cat in seed_config.CATEGORIES:
            bind.execute(
                sa.text(
                    "UPDATE franchise_categories "
                    "SET synergy_map = CAST(:synergy_map AS jsonb) "
                    "WHERE slug = :slug"
                ),
                {"synergy_map": json.dumps(cat["synergy_map"]), "slug": cat["slug"]},
            )


def downgrade() -> None:
    op.drop_column("franchise_categories", "synergy_map")
    op.drop_table("disaster_risks")
