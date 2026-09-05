"""Registration validates eagerly, so a misconfiguration fails at `add` time
rather than during the first discovery run half an hour later."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError, UnknownDatasourceError
from genql.registries.errors import UnknownRegistryKeyError
from genql.services.datasource.datasource_service import DatasourceService

ENV = {"GENQL_WH2_DSN": "postgresql+psycopg://u:p@host/db"}


class FakeDatasources:
    def __init__(self) -> None:
        self.rows: dict[str, Datasource] = {}

    def add(self, datasource: Datasource) -> None:
        self.rows[datasource.name] = datasource

    def get(self, name: str) -> Datasource:
        try:
            return self.rows[name]
        except KeyError:
            raise UnknownDatasourceError(name, sorted(self.rows)) from None

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return [d for d in self.rows.values() if d.enabled or not enabled_only]

    def remove(self, name: str) -> None:
        self.get(name)
        del self.rows[name]


def _service(repo: FakeDatasources) -> DatasourceService:
    return DatasourceService(datasources=repo, dialects=["postgres"], env=ENV)


def test_register_persists_the_datasource() -> None:
    repo = FakeDatasources()

    created = _service(repo).register("wh2", "postgres", "GENQL_WH2_DSN", None)

    assert created.name == "wh2"
    assert repo.rows["wh2"].dsn_env_var == "GENQL_WH2_DSN"


def test_register_refuses_an_unregistered_dialect() -> None:
    with pytest.raises(UnknownRegistryKeyError):
        _service(FakeDatasources()).register("wh2", "db2", "GENQL_WH2_DSN", None)


def test_register_refuses_a_datasource_whose_secret_is_missing() -> None:
    with pytest.raises(MissingDatasourceSecretError, match="GENQL_ABSENT_DSN"):
        _service(FakeDatasources()).register("wh2", "postgres", "GENQL_ABSENT_DSN", None)


def test_remove_delegates_to_the_repository() -> None:
    repo = FakeDatasources()
    service = _service(repo)
    service.register("wh2", "postgres", "GENQL_WH2_DSN", None)

    service.remove("wh2")

    assert repo.rows == {}
