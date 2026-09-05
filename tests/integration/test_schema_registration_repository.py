from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.semantic.datasource_repository import PostgresDatasourceRepository
from genql.repositories.semantic.schema_registration_repository import (
    PostgresSchemaRegistrationRepository,
)

DS = Datasource(name="reg_ds", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
REF = SchemaRef(datasource_name="reg_ds", schema_name="sales")


@pytest.fixture()
def repo(migrated_engine: Engine) -> PostgresSchemaRegistrationRepository:
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM genql.genql_datasource WHERE name = 'reg_ds'"))
    PostgresDatasourceRepository(engine=migrated_engine).add(DS)
    return PostgresSchemaRegistrationRepository(engine=migrated_engine)


def test_add_then_get_round_trips(repo: PostgresSchemaRegistrationRepository) -> None:
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="sales"))

    stored = repo.get(REF)

    assert stored.ref == REF
    assert stored.enabled is True
    assert stored.last_discovered_at is None


def test_get_unknown_raises(repo: PostgresSchemaRegistrationRepository) -> None:
    with pytest.raises(UnknownSchemaRegistrationError):
        repo.get(SchemaRef(datasource_name="reg_ds", schema_name="absent"))


def test_list_for_datasource_can_filter_to_enabled(
    repo: PostgresSchemaRegistrationRepository,
) -> None:
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="sales"))
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="stale", enabled=False))

    names = {r.schema_name for r in repo.list_for_datasource("reg_ds", enabled_only=True)}

    assert names == {"sales"}


def test_mark_discovered_stamps_a_timestamp(repo: PostgresSchemaRegistrationRepository) -> None:
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="sales"))

    repo.mark_discovered(REF)

    assert repo.get(REF).last_discovered_at is not None


def test_remove_deletes_the_registration(repo: PostgresSchemaRegistrationRepository) -> None:
    repo.add(SchemaRegistration(datasource_name="reg_ds", schema_name="sales"))
    repo.remove(REF)
    with pytest.raises(UnknownSchemaRegistrationError):
        repo.get(REF)
