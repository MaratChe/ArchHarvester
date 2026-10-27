"""Initial registry and provenance storage."""
from alembic import op
from sqlalchemy import Column, ForeignKey, Integer, JSON, MetaData, String, Table, UniqueConstraint

revision = "0001"
down_revision = None


def upgrade():
    # Freeze migration definitions independently of future application models.
    m = MetaData()
    Table("artifact_types", m, Column("id", String, primary_key=True), Column("type_key", String, nullable=False), Column("version", Integer, nullable=False), Column("data", JSON, nullable=False), UniqueConstraint("type_key", "version"))
    Table("artifacts", m, Column("id", String, primary_key=True), Column("type_id", ForeignKey("artifact_types.id"), nullable=False), Column("data", JSON, nullable=False))
    Table("revisions", m, Column("artifact_id", ForeignKey("artifacts.id"), primary_key=True), Column("revision", Integer, primary_key=True), Column("data", JSON, nullable=False))
    Table("resources", m, Column("id", String, primary_key=True), Column("data", JSON, nullable=False))
    Table("snapshots", m, Column("id", String, primary_key=True), Column("resource_id", ForeignKey("resources.id"), nullable=False), Column("digest", String, nullable=False), Column("data", JSON, nullable=False), UniqueConstraint("resource_id", "digest"))
    Table("source_links", m, Column("resource_id", ForeignKey("resources.id"), primary_key=True), Column("type_id", ForeignKey("artifact_types.id"), primary_key=True), Column("artifact_id", ForeignKey("artifacts.id"), nullable=False))
    Table("candidates", m, Column("id", String, primary_key=True), Column("result_key", String, nullable=False, unique=True), Column("data", JSON, nullable=False))
    m.create_all(op.get_bind())
    op.execute("CREATE VIRTUAL TABLE artifact_fts USING fts5(id UNINDEXED, content, tokenize='unicode61')")


def downgrade():
    raise RuntimeError("Restore a backup instead of destroying registry history")
