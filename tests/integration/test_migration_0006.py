"""The negative assertions are the point. A read-only role that can SELECT is
easy to get right by accident; one that genuinely cannot INSERT, DELETE, or
DROP is what the guarded execution path depends on."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from genql.infrastructure.db.engine import create_engine_from_dsn


@pytest.fixture()
def readonly_engine(migrated_engine: Engine, paradedb_dsn: str) -> Engine:
    url = make_url(paradedb_dsn).set(
        username="genql_readonly", password=os.environ["GENQL_READONLY_DB_PASSWORD"]
    )
    return create_engine_from_dsn(url.render_as_string(hide_password=False))


def test_the_role_exists_after_upgrade(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genql_readonly')")
        ).scalar_one()

    assert exists is True


@pytest.mark.skipif_no_tpcds
def test_the_role_can_select_from_a_seeded_table(readonly_engine: Engine) -> None:
    with readonly_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM tpcds.store")).scalar_one()

    assert count >= 0


@pytest.mark.skipif_no_tpcds
def test_the_role_cannot_insert(readonly_engine: Engine) -> None:
    with pytest.raises(DBAPIError, match="permission denied"), readonly_engine.begin() as conn:
        conn.execute(text("INSERT INTO tpcds.store (s_store_sk) VALUES (-1)"))


@pytest.mark.skipif_no_tpcds
def test_the_role_cannot_delete(readonly_engine: Engine) -> None:
    with pytest.raises(DBAPIError, match="permission denied"), readonly_engine.begin() as conn:
        conn.execute(text("DELETE FROM tpcds.store"))


@pytest.mark.skipif_no_tpcds
def test_the_role_cannot_drop(readonly_engine: Engine) -> None:
    with pytest.raises(DBAPIError, match="must be owner"), readonly_engine.begin() as conn:
        conn.execute(text("DROP TABLE tpcds.store"))


def test_the_role_can_read_a_table_created_after_the_grant(
    migrated_engine: Engine, readonly_engine: Engine
) -> None:
    """pg_read_all_data covers objects created later, which per-schema GRANTs do not."""
    with migrated_engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS public.after_the_grant (n int)"))
        conn.execute(text("INSERT INTO public.after_the_grant (n) VALUES (7)"))
    try:
        with readonly_engine.connect() as conn:
            value = conn.execute(text("SELECT n FROM public.after_the_grant")).scalar_one()
        assert value == 7
    finally:
        with migrated_engine.begin() as conn:
            conn.execute(text("DROP TABLE public.after_the_grant"))
