"""Settings.semantic_dsn is a SQLAlchemy URL; psycopg needs libpq form.

This exists so there is exactly ONE setting naming GenQL's own database. A
second setting for the same database would let the checkpointer and the
semantic store drift onto different servers, which would fail silently — the
checkpoints would simply never be found again.
"""

from __future__ import annotations

import pytest

from genql.infrastructure.db.psycopg_dsn import to_libpq_dsn


def test_the_sqlalchemy_driver_token_is_stripped() -> None:
    assert (
        to_libpq_dsn("postgresql+psycopg://genql:genql@localhost:5433/genql")
        == "postgresql://genql:genql@localhost:5433/genql"
    )


def test_any_driver_token_is_stripped_not_just_psycopg() -> None:
    assert to_libpq_dsn("postgresql+psycopg2://u:p@h:5432/d") == "postgresql://u:p@h:5432/d"


def test_a_plain_libpq_dsn_passes_through_unchanged() -> None:
    assert to_libpq_dsn("postgresql://u:p@h:5432/d") == "postgresql://u:p@h:5432/d"


def test_the_postgres_scheme_alias_is_accepted() -> None:
    assert to_libpq_dsn("postgres://u:p@h:5432/d") == "postgres://u:p@h:5432/d"


def test_query_parameters_survive() -> None:
    assert (
        to_libpq_dsn("postgresql+psycopg://u:p@h:5432/d?sslmode=require")
        == "postgresql://u:p@h:5432/d?sslmode=require"
    )


def test_a_non_postgres_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="postgres"):
        to_libpq_dsn("mysql://u:p@h:3306/d")
