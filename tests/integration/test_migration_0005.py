"""Purely additive: six new tables, two extensions, one BM25 index, one HNSW
index. Downgrade drops the tables but never the extensions — another table
in the same database might still need them."""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text


def test_upgrade_creates_the_six_tables_and_both_indexes(engine: Engine, paradedb_dsn: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        tables = set(
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'genql' AND table_name LIKE 'genql_%'"
                )
            ).scalars()
        )
        indexes = set(
            conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'genql' AND tablename = 'genql_search_document'"
                )
            ).scalars()
        )

    assert {
        "genql_object_enrichment",
        "genql_column_enrichment",
        "genql_domain",
        "genql_domain_member",
        "genql_metric",
        "genql_search_document",
    } <= tables
    assert "genql_search_document_bm25" in indexes
    assert "genql_search_document_hnsw" in indexes


def test_downgrade_then_upgrade_is_clean(engine: Engine, paradedb_dsn: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "0004")
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('genql.genql_search_document') IS NOT NULL")
        ).scalar_one()
    assert exists
