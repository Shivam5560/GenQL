"""Guards the properties of TPC-DS that make it the right discovery fixture."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

CRYPTIC = ["ss_ext_sales_price", "d_moy", "cd_demo_sk"]


@pytest.mark.skipif_no_tpcds
def test_schema_has_the_expected_object_count(engine: Engine) -> None:
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM pg_tables WHERE schemaname = 'tpcds'")
        ).scalar_one()
    assert count >= 24


@pytest.mark.skipif_no_tpcds
def test_cryptic_column_names_are_present(engine: Engine) -> None:
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'tpcds'"
                )
            )
        }
    assert set(CRYPTIC).issubset(names)


@pytest.mark.skipif_no_tpcds
def test_seed_script_added_the_tpcds_foreign_key_graph(engine: Engine) -> None:
    """DuckDB's dsdgen emits zero constraints; data/seed_tpcds.py adds TPC-DS's
    documented primary/foreign keys after loading. Phase 3's graph projection
    depends on this. See final-review.md I5 / triage item 2.
    """
    with engine.connect() as conn:
        fk_count = conn.execute(
            text(
                "SELECT count(*) FROM pg_constraint con "
                "JOIN pg_class cl ON cl.oid = con.conrelid "
                "JOIN pg_namespace n ON n.oid = cl.relnamespace "
                "WHERE n.nspname = 'tpcds' AND con.contype = 'f'"
            )
        ).scalar_one()
    assert fk_count > 0

    with engine.connect() as conn:
        store_sales_reltuples = conn.execute(
            text(
                "SELECT reltuples FROM pg_class "
                "WHERE relname = 'store_sales' "
                "AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'tpcds')"
            )
        ).scalar_one()
    # ANALYZE ran as part of the seed, so reltuples must be a real (non-sentinel)
    # estimate, not the -1 "never analyzed" sentinel — see final-review.md I1.
    assert store_sales_reltuples >= 0
