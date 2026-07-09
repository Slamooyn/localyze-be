"""auth: users table + user_id ownership on analyses & user_outlets

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-09

Written defensively: migration 0001 builds the schema from live model metadata, so a
FRESH database already has `users` and the `user_id` columns. This migration only
fills the gap on a database that was migrated under the v1 models.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine.reflection import Inspector

from app.db import Base
from app import models  # noqa: F401

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = Inspector.from_engine(bind)
    tables = set(insp.get_table_names())

    if "users" not in tables:
        Base.metadata.tables["users"].create(bind)

    for table in ("analyses", "user_outlets"):
        cols = {c["name"] for c in insp.get_columns(table)}
        if "user_id" not in cols:
            # Pre-auth rows have no owner and cannot be assigned; a fresh seed
            # recreates the demo user's data. Safe to clear in this demo build.
            op.execute(f"DELETE FROM {table}")
            op.add_column(
                table,
                sa.Column(
                    "user_id",
                    UUID(as_uuid=True),
                    sa.ForeignKey("users.id"),
                    nullable=False,
                ),
            )

    idx = {i["name"] for i in insp.get_indexes("analyses")}
    if "idx_analyses_user" not in idx:
        op.create_index("idx_analyses_user", "analyses", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_analyses_user", table_name="analyses")
    op.drop_column("user_outlets", "user_id")
    op.drop_column("analyses", "user_id")
    op.drop_table("users")
