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
