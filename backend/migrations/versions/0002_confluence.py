"""Persist read-only Confluence configuration, selections and resumable jobs."""
from alembic import op
from sqlalchemy import Column, Float, JSON, String

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table("confluence_connections", Column("id", String, primary_key=True), Column("base_url", String, nullable=False, unique=True), Column("data", JSON, nullable=False))
    op.create_table("confluence_previews", Column("id", String, primary_key=True), Column("data", JSON, nullable=False))
    op.create_table("confluence_jobs", Column("id", String, primary_key=True), Column("data", JSON, nullable=False), Column("owner", String), Column("lease_until", Float, nullable=False, server_default="0"))


def downgrade():
    raise RuntimeError("Restore a backup instead of destroying import history")
