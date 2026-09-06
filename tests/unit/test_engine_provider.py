"""The provider resolves a DSN from an injected environment, never os.environ.

Injecting the mapping is what lets this run as a unit test: nothing here
mutates process state, and no test needs monkeypatch to describe a datasource
whose secret is missing.
"""

from __future__ import annotations

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError, MissingReadonlySecretError
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
