"""0008 is one additive table, mirroring genql_search_document's pgvector/HNSW
shape exactly (same extension, same index type, same distance operator) so
nothing new is asked of the ParadeDB image. domain_id is ON DELETE SET NULL,
not CASCADE: an example survives its domain being renamed or re-clustered,
since the question/interpretations/resolution triple is still a valid few-shot
exemplar even once it is no longer attributed to a specific domain.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text


@pytest.fixture()
def alembic_config(paradedb_dsn: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    return cfg


def test_upgrade_creates_genql_ambiguity_example(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text("SELECT to_regclass('genql.genql_ambiguity_example') IS NOT NULL")
        ).scalar_one()

    assert present


def test_the_hnsw_index_exists(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text("SELECT count(*) FROM pg_indexes WHERE indexname = 'genql_ambiguity_example_hnsw'")
        ).scalar_one()

    assert present == 1


def test_deleting_a_domain_sets_domain_id_null_rather_than_deleting_the_row(
    migrated_engine: Engine, register_schema: object
) -> None:
    register_schema("ambiguity_ds", "public")  # type: ignore[operator]
    with migrated_engine.begin() as conn:
        domain_id = conn.execute(
            text(
                "INSERT INTO genql.genql_domain (datasource_name, name, description) "
                "VALUES ('ambiguity_ds', 'Sales', 'd') RETURNING id"
            )
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO genql.genql_ambiguity_example "
                "(domain_id, question, interpretations, resolution, embedding) "
                "VALUES (:domain_id, 'q', ARRAY['a','b'], 'r', "
                "CAST(ARRAY(SELECT 0 FROM generate_series(1,1536)) AS vector))"
            ),
            {"domain_id": domain_id},
        )
        conn.execute(text("DELETE FROM genql.genql_domain WHERE id = :id"), {"id": domain_id})
        remaining = conn.execute(
            text("SELECT domain_id FROM genql.genql_ambiguity_example WHERE question = 'q'")
        ).scalar_one()

    assert remaining is None


def test_downgrade_to_0007_drops_genql_ambiguity_example_and_upgrade_restores_it(
    migrated_engine: Engine, alembic_config: Config
) -> None:
    command.downgrade(alembic_config, "0007")
    with migrated_engine.connect() as conn:
        gone = conn.execute(
            text("SELECT to_regclass('genql.genql_ambiguity_example') IS NULL")
        ).scalar_one()
    assert gone

    command.upgrade(alembic_config, "head")
    with migrated_engine.connect() as conn:
        back = conn.execute(
            text("SELECT to_regclass('genql.genql_ambiguity_example') IS NOT NULL")
        ).scalar_one()
    assert back
