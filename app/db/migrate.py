"""Run Alembic migrations from inside the app (no alembic.ini needed in production)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

_SCRIPTS = Path(__file__).resolve().parent.parent / "migrations"


def _config(engine: Engine) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_SCRIPTS))
    return cfg


def upgrade(engine: Engine) -> None:
    """Bring the schema to head. A DB created before Alembic existed (early create_all() builds) has exactly the
    0001 schema: it is stamped with that revision, then upgraded like any other, so its data is kept."""
    cfg = _config(engine)
    tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        if "alembic_version" not in tables and "job_log" in tables:
            command.stamp(cfg, "0001")
        command.upgrade(cfg, "head")
