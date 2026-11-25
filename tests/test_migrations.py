"""Tests for Alembic database migrations."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_and_downgrade(tmp_path: Path) -> None:
    db_file = tmp_path / "test_migrations.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    repo_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(repo_root / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", str(repo_root / "src/context_substrate/migrations")
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    tables = set(inspect(engine).get_table_names())
    assert "source_records" in tables
    assert "sync_cursors" in tables
    engine.dispose()

    command.downgrade(alembic_cfg, "base")

    engine = create_engine(db_url)
    tables_after = set(inspect(engine).get_table_names())
    assert "source_records" not in tables_after
    assert "sync_cursors" not in tables_after
    engine.dispose()
