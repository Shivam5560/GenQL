"""The provider resolves a DSN from an injected environment, never os.environ.

Injecting the mapping is what lets this run as a unit test: nothing here
mutates process state, and no test needs monkeypatch to describe a datasource
whose secret is missing.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import (
    MissingDatasourceSecretError,
    MissingReadonlySecretError,
    UndecryptableDatasourceSecretError,
)
from genql.infrastructure.db.engine_provider import DatasourceEngineProvider

DS = Datasource(name="wh2", dialect="postgres", dsn_env_var="GENQL_WH2_DSN")


class FakeEngine:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn


def _provider(env: dict[str, str]) -> DatasourceEngineProvider:
    return DatasourceEngineProvider(env=env, engine_factory=FakeEngine)  # type: ignore[arg-type]


def test_engine_is_built_from_the_named_environment_variable() -> None:
    provider = _provider({"GENQL_WH2_DSN": "postgresql+psycopg://u:p@host/db"})

    engine = provider.engine_for(DS)

    assert engine.dsn == "postgresql+psycopg://u:p@host/db"  # type: ignore[attr-defined]


def test_the_same_datasource_gets_the_same_engine() -> None:
    provider = _provider({"GENQL_WH2_DSN": "postgresql+psycopg://u:p@host/db"})

    assert provider.engine_for(DS) is provider.engine_for(DS)


def test_a_missing_variable_raises_a_typed_error_naming_both() -> None:
    provider = _provider({})

    with pytest.raises(MissingDatasourceSecretError, match="GENQL_WH2_DSN"):
        provider.engine_for(DS)


def test_an_empty_variable_is_treated_as_missing() -> None:
    provider = _provider({"GENQL_WH2_DSN": "   "})

    with pytest.raises(MissingDatasourceSecretError):
        provider.engine_for(DS)


def test_invalidate_drops_the_cached_engine() -> None:
    provider = _provider({"GENQL_WH2_DSN": "postgresql+psycopg://u:p@host/db"})
    first = provider.engine_for(DS)

    provider.invalidate("wh2")

    assert provider.engine_for(DS) is not first


def test_the_readonly_engine_swaps_the_role_and_password_into_the_dsn() -> None:
    provider = DatasourceEngineProvider(
        env={"GENQL_WH2_DSN": "postgresql+psycopg://genql:genql@host:5433/genql"},
        engine_factory=FakeEngine,  # type: ignore[arg-type]
        readonly_password="s3cret",
    )

    engine = provider.readonly_engine_for(DS)

    assert engine.dsn == "postgresql+psycopg://genql_readonly:s3cret@host:5433/genql"  # type: ignore[attr-defined]


def test_the_readonly_engine_is_cached_separately_from_the_admin_engine() -> None:
    provider = DatasourceEngineProvider(
        env={"GENQL_WH2_DSN": "postgresql+psycopg://genql:genql@host:5433/genql"},
        engine_factory=FakeEngine,  # type: ignore[arg-type]
        readonly_password="s3cret",
    )

    admin = provider.engine_for(DS)
    readonly = provider.readonly_engine_for(DS)

    assert admin is not readonly
    assert provider.readonly_engine_for(DS) is readonly


def test_a_missing_readonly_password_raises_a_typed_error() -> None:
    provider = _provider({"GENQL_WH2_DSN": "postgresql+psycopg://genql:genql@host:5433/genql"})

    with pytest.raises(MissingReadonlySecretError, match="wh2"):
        provider.readonly_engine_for(DS)


STORED = Datasource(
    name="wh3",
    dialect="postgres",
    host="warehouse.internal",
    port=5433,
    database="analytics",
    username="reader",
    password_ciphertext="terc3s",
)


class ReversingCipher:
    def encrypt(self, plaintext: str) -> str:
        return plaintext[::-1]

    def decrypt(self, ciphertext: str) -> str:
        return ciphertext[::-1]


def test_a_stored_endpoint_is_assembled_into_a_dsn_with_the_password_decrypted() -> None:
    provider = DatasourceEngineProvider(
        env={},
        cipher=ReversingCipher(),
        engine_factory=FakeEngine,  # type: ignore[arg-type]
    )

    engine = provider.engine_for(STORED)

    assert engine.dsn == "postgresql+psycopg://reader:s3cret@warehouse.internal:5433/analytics"  # type: ignore[attr-defined]


def test_a_stored_endpoint_needs_no_environment_variable_at_all() -> None:
    """The whole point of the connect form: nothing about this datasource is
    configured on the server."""
    provider = DatasourceEngineProvider(
        env={},
        cipher=ReversingCipher(),
        engine_factory=FakeEngine,  # type: ignore[arg-type]
    )

    assert provider.engine_for(STORED) is not None


def test_a_datasource_with_neither_endpoint_nor_variable_names_the_problem() -> None:
    orphan = Datasource(name="broken", dialect="postgres")

    with pytest.raises(MissingDatasourceSecretError, match="broken"):
        _provider({}).engine_for(orphan)


def test_a_stored_credential_that_will_not_decrypt_says_so() -> None:
    """A rotated GENQL_SECRET_KEY, not a corrupt row — and the message has to
    say which, because the fixes are different."""

    class RefusingCipher:
        def encrypt(self, plaintext: str) -> str:
            return plaintext

        def decrypt(self, ciphertext: str) -> str:
            raise InvalidToken

    provider = DatasourceEngineProvider(
        env={},
        cipher=RefusingCipher(),
        engine_factory=FakeEngine,  # type: ignore[arg-type]
    )

    with pytest.raises(UndecryptableDatasourceSecretError, match="wh3"):
        provider.engine_for(STORED)


def test_a_password_with_url_metacharacters_survives_the_round_trip() -> None:
    """`p@ss/word` concatenated naively produces a DSN pointing at a host
    called `ss`, which fails at connect time with a name-resolution error
    nobody would trace back to the password field."""
    provider = DatasourceEngineProvider(
        env={},
        cipher=ReversingCipher(),
        engine_factory=FakeEngine,  # type: ignore[arg-type]
    )

    engine = provider.engine_for(STORED.model_copy(update={"password_ciphertext": "drow/ss@p"}))

    assert "p%40ss%2Fword" in engine.dsn  # type: ignore[attr-defined]
    assert engine.dsn.endswith("@warehouse.internal:5433/analytics")  # type: ignore[attr-defined]


def test_invalidate_drops_both_bindings() -> None:
    provider = DatasourceEngineProvider(
        env={"GENQL_WH2_DSN": "postgresql+psycopg://genql:genql@host:5433/genql"},
        engine_factory=FakeEngine,  # type: ignore[arg-type]
        readonly_password="s3cret",
    )
    admin = provider.engine_for(DS)
    readonly = provider.readonly_engine_for(DS)

    provider.invalidate("wh2")

    assert provider.engine_for(DS) is not admin
    assert provider.readonly_engine_for(DS) is not readonly
