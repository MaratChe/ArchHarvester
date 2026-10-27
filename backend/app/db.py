"""SQLite persistence. Writers reserve a transaction before checking revisions."""
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import Column, Float, ForeignKey, Integer, JSON, MetaData, String, Table, UniqueConstraint, create_engine, event
from alembic import command
from alembic.config import Config

metadata = MetaData()
providers = Table('model_providers',metadata,Column('id',String,primary_key=True),Column('data',JSON,nullable=False))
search_indexes = Table("search_indexes", metadata, Column("id", String, primary_key=True), Column("data", JSON, nullable=False))
search_vectors = Table("search_vectors", metadata, Column("id", String, primary_key=True), Column("index_id", String, nullable=False), Column("data", JSON, nullable=False))
llm_outputs = Table("llm_outputs", metadata, Column("id", String, primary_key=True), Column("expires", Float, nullable=False), Column("data", JSON, nullable=False))
pipelines = Table("pipelines", metadata, Column("id", String, primary_key=True), Column("pipeline_key", String, nullable=False), Column("version", Integer, nullable=False), Column("data", JSON, nullable=False), UniqueConstraint("pipeline_key", "version"))
pipeline_tests = Table("pipeline_tests", metadata, Column("id", String, primary_key=True), Column("data", JSON, nullable=False))
types = Table("artifact_types", metadata, Column("id", String, primary_key=True), Column("type_key", String, nullable=False), Column("version", Integer, nullable=False), Column("data", JSON, nullable=False), UniqueConstraint("type_key", "version"))
artifacts = Table("artifacts", metadata, Column("id", String, primary_key=True), Column("type_id", ForeignKey("artifact_types.id"), nullable=False), Column("data", JSON, nullable=False))
revisions = Table("revisions", metadata, Column("artifact_id", ForeignKey("artifacts.id"), primary_key=True), Column("revision", Integer, primary_key=True), Column("data", JSON, nullable=False))
resources = Table("resources", metadata, Column("id", String, primary_key=True), Column("data", JSON, nullable=False))
snapshots = Table("snapshots", metadata, Column("id", String, primary_key=True), Column("resource_id", ForeignKey("resources.id"), nullable=False), Column("digest", String, nullable=False), Column("data", JSON, nullable=False), UniqueConstraint("resource_id", "digest"))
links = Table("source_links", metadata, Column("resource_id", ForeignKey("resources.id"), primary_key=True), Column("type_id", ForeignKey("artifact_types.id"), primary_key=True), Column("artifact_id", ForeignKey("artifacts.id"), nullable=False))
candidates = Table("candidates", metadata, Column("id", String, primary_key=True), Column("result_key", String, nullable=False, unique=True), Column("data", JSON, nullable=False))
connections = Table("confluence_connections", metadata, Column("id", String, primary_key=True), Column("base_url", String, nullable=False, unique=True), Column("data", JSON, nullable=False))
previews = Table("confluence_previews", metadata, Column("id", String, primary_key=True), Column("data", JSON, nullable=False))
jobs = Table("confluence_jobs", metadata, Column("id", String, primary_key=True), Column("data", JSON, nullable=False), Column("owner", String), Column("lease_until", Float, nullable=False, default=0))


class Database:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "blobs").mkdir(exist_ok=True)
        self.engine = create_engine("sqlite:///" + (directory / "registry.db").as_posix(), connect_args={"check_same_thread": False, "timeout": 15})

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    @contextmanager
    def transaction(self):
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise


def find(connection, table, id):
    return connection.execute(table.select().where(table.c.id == id)).mappings().first()
