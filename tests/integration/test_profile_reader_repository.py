from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.column import Column
from genql.repositories.warehouse.profile_reader_repository import (
    PostgresProfileReaderRepository,
)

FIXTURE = """
DROP SCHEMA IF EXISTS prof CASCADE;
CREATE SCHEMA prof;
CREATE TABLE prof.payment (id BIGINT, kind TEXT);
INSERT INTO prof.payment (id, kind)
SELECT g, (ARRAY['CREDIT','DEBIT','TRANSFER'])[1 + g % 3] FROM generate_series(1, 90) g;
INSERT INTO prof.payment (id, kind) VALUES (91, NULL), (92, NULL);
"""


@pytest.fixture(scope="module")
def prof_schema(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(text(FIXTURE))
    return engine


def _column(name: str, data_type: str) -> Column:
    return Column(
        schema_name="prof",
        object_name="payment",
        column_name=name,
        ordinal=1,
        data_type=data_type,
        is_nullable=True,
    )


def test_profiles_distinct_count_and_samples(prof_schema: Engine) -> None:
    repo = PostgresProfileReaderRepository(prof_schema)
    profile = repo.profile_column(_column("kind", "text"), sample_limit=5)

    assert profile.distinct_count == 3
    assert set(profile.sample_values) <= {"CREDIT", "DEBIT", "TRANSFER"}
    assert profile.null_fraction == pytest.approx(2 / 92, abs=1e-3)


def test_sample_limit_is_respected(prof_schema: Engine) -> None:
    repo = PostgresProfileReaderRepository(prof_schema)
    profile = repo.profile_column(_column("id", "bigint"), sample_limit=2)
    assert len(profile.sample_values) == 2


def test_identifiers_are_quoted_not_interpolated(prof_schema: Engine) -> None:
    """A hostile column name must not become SQL."""
    with prof_schema.begin() as conn:
        conn.execute(text('ALTER TABLE prof.payment ADD COLUMN "weird ""name" TEXT'))
    repo = PostgresProfileReaderRepository(prof_schema)
    profile = repo.profile_column(_column('weird "name', "text"), sample_limit=5)
    assert profile.distinct_count == 0
