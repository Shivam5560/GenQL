"""0013 lets a datasource carry its own credentials.

Two properties are worth a real database rather than a unit test. The CHECK
constraint is one — a row that says where its warehouse is twice, or not at
all, is exactly the half-written registration that would otherwise surface as
a connection failure minutes into an ingestion run, and only Postgres can
prove the constraint refuses it. The other is that `local` survives: it names
an environment variable and has no host, and a migration that broke it would
break the datasource this whole project was developed against.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from genql.domain.value_objects.datasource_connection import DatasourceConnection
from genql.infrastructure.auth.fernet_secret_cipher import FernetSecretCipher
from genql.infrastructure.db.dsn_schemes import DSN_SCHEMES
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider
from genql.repositories.semantic.datasource_repository import PostgresDatasourceRepository
from genql.services.datasource.datasource_service import DatasourceService


class NoEngines:
    def invalidate(self, name: str) -> None:
        pass


@pytest.fixture()
def cipher() -> FernetSecretCipher:
    return FernetSecretCipher(Fernet.generate_key().decode())


@pytest.fixture()
def service(migrated_engine: Engine, cipher: FernetSecretCipher) -> DatasourceService:
    return DatasourceService(
        datasources=PostgresDatasourceRepository(migrated_engine),
        dialects=["postgres"],
        dialect_registry="catalog_readers",
        dsn_schemes=DSN_SCHEMES,
        cipher=cipher,
        env={},
        engines=NoEngines(),
    )


@pytest.fixture()
def registered(service: DatasourceService, migrated_engine: Engine) -> str:
    name = "mig13_wh"
    service.register(
        name,
        "postgres",
        DatasourceConnection(
            host="warehouse.internal",
            port=6543,
            database="analytics",
            username="reader",
            # Both characters that break naive DSN concatenation, on purpose.
            password="p@ss/word",
            options="sslmode=require",
        ),
        "registered by the connect form",
    )
    yield name
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM genql.genql_datasource WHERE name = :n"), {"n": name})


def test_the_stored_row_holds_no_readable_credential(
    migrated_engine: Engine, registered: str
) -> None:
    with migrated_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT host, port, database, username, password_ciphertext "
                "FROM genql.genql_datasource WHERE name = :n"
            ),
            {"n": registered},
        ).one()

    assert (row.host, row.port, row.database, row.username) == (
        "warehouse.internal",
        6543,
        "analytics",
        "reader",
    )
    assert "p@ss/word" not in row.password_ciphertext


def test_the_row_round_trips_back_into_a_usable_dsn(
    migrated_engine: Engine, cipher: FernetSecretCipher, registered: str
) -> None:
    repository = PostgresDatasourceRepository(migrated_engine)
    provider = DatasourceEngineProvider(env={}, cipher=cipher, engine_factory=lambda dsn: dsn)  # type: ignore[arg-type]

    dsn = provider.engine_for(repository.get(registered))

    assert dsn == (
        "postgresql+psycopg://reader:p%40ss%2Fword@warehouse.internal:6543/analytics"
        "?sslmode=require"
    )


def test_the_migrated_local_datasource_still_names_its_environment_variable(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.connect() as conn:
        row = conn.execute(
            text("SELECT dsn_env_var, host FROM genql.genql_datasource WHERE name = 'local'")
        ).one()

    assert row.dsn_env_var == "GENQL_WAREHOUSE_DSN"
    assert row.host is None


@pytest.mark.parametrize(
    ("sql", "why"),
    [
        (
            "INSERT INTO genql.genql_datasource (name, dialect, dsn_env_var, host, port) "
            "VALUES ('mig13_both', 'postgres', 'SOME_DSN', 'h', 5432)",
            "says where it is twice",
        ),
        (
            "INSERT INTO genql.genql_datasource (name, dialect) "
            "VALUES ('mig13_neither', 'postgres')",
            "never says where it is",
        ),
    ],
)
def test_a_row_must_name_its_warehouse_exactly_one_way(
    migrated_engine: Engine, sql: str, why: str
) -> None:
    with pytest.raises(IntegrityError), migrated_engine.begin() as conn:
        conn.execute(text(sql))
