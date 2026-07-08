"""initial schema — all 8 tables + PostGIS

Revision ID: 0001
Revises:
Create Date: 2026-07-08

The schema is created directly from the SQLAlchemy metadata so it stays 1:1 with
app/models (the single source of truth). PostGIS must exist before the geography /
geometry columns are created.
"""
from typing import Sequence, Union

from alembic import op

from app.db import Base
from app import models  # noqa: F401  (populate Base.metadata)

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
