"""Versioned extraction rules and immutable test runs."""
from alembic import op
from sqlalchemy import Column, JSON, String, Integer, UniqueConstraint
revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table("pipelines", Column("id", String, primary_key=True), Column("pipeline_key", String, nullable=False), Column("version", Integer, nullable=False), Column("data", JSON, nullable=False), UniqueConstraint("pipeline_key", "version"))
    op.create_table("pipeline_tests", Column("id", String, primary_key=True), Column("data", JSON, nullable=False))


def downgrade():
    raise RuntimeError("Restore a backup instead of destroying pipeline history")
