"""The provider resolves a DSN from an injected environment, never os.environ.

Injecting the mapping is what lets this run as a unit test: nothing here
mutates process state, and no test needs monkeypatch to describe a datasource
whose secret is missing.
"""

from __future__ import annotations

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError
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
