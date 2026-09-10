"""Registration validates eagerly, so a misconfiguration fails at `add` time
rather than during the first discovery run half an hour later.

Both registration paths are covered: by endpoint (the connect form, which
stores an encrypted password) and by environment variable (the CLI and every
datasource that predates stored credentials).
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import MissingDatasourceSecretError, UnknownDatasourceError
from genql.domain.value_objects.datasource_connection import DatasourceConnection
from genql.registries.errors import UnknownRegistryKeyError
from genql.services.datasource.datasource_service import DatasourceService

ENV = {"GENQL_WH2_DSN": "postgresql+psycopg://u:p@host/db"}

CONNECTION = DatasourceConnection(
    host="warehouse.internal", port=5432, database="analytics", username="reader", password="s3cret"
)


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


class FakeEngines:
    def __init__(self) -> None:
        self.invalidated: list[str] = []

    def invalidate(self, name: str) -> None:
        self.invalidated.append(name)


class ReversingCipher:
    """Enough of a cipher to prove the service encrypts on the way in.

    Reversible and obviously not secret, which is the point: a test that
    asserted on a real Fernet token could only assert that it is not the
    plaintext, and this asserts what was encrypted as well.
    """

    def encrypt(self, plaintext: str) -> str:
        return plaintext[::-1]

    def decrypt(self, ciphertext: str) -> str:
        return ciphertext[::-1]


def _service(repo: FakeDatasources, engines: FakeEngines | None = None) -> DatasourceService:
    return DatasourceService(
        datasources=repo,
        dialects=["postgres"],
        dialect_registry="catalog_readers",
        dsn_schemes={"postgres": "postgresql+psycopg"},
        cipher=ReversingCipher(),
        env=ENV,
        engines=engines or FakeEngines(),
    )


def test_register_persists_the_endpoint() -> None:
    repo = FakeDatasources()

    created = _service(repo).register("wh2", "postgres", CONNECTION, None)

    assert created.name == "wh2"
    assert repo.rows["wh2"].endpoint == "warehouse.internal:5432/analytics"
    assert repo.rows["wh2"].username == "reader"


def test_register_stores_the_password_encrypted_and_never_in_the_clear() -> None:
    repo = FakeDatasources()

    _service(repo).register("wh2", "postgres", CONNECTION, None)

    stored = repo.rows["wh2"]
    assert stored.password_ciphertext == "terc3s"
    assert "s3cret" not in stored.model_dump_json()


def test_register_leaves_the_ciphertext_empty_when_there_is_no_password() -> None:
    """A warehouse reachable by trust or client certificate has no password,
    and an encrypted empty string would read as one that does."""
    repo = FakeDatasources()

    _service(repo).register("wh2", "postgres", CONNECTION.model_copy(update={"password": ""}), None)

    assert repo.rows["wh2"].password_ciphertext is None


def test_register_refuses_an_unregistered_dialect() -> None:
    with pytest.raises(UnknownRegistryKeyError):
        _service(FakeDatasources()).register("wh2", "db2", CONNECTION, None)


def test_register_from_env_persists_the_variable_name() -> None:
    repo = FakeDatasources()

    created = _service(repo).register_from_env("wh2", "postgres", "GENQL_WH2_DSN", None)

    assert created.dsn_env_var == "GENQL_WH2_DSN"
    assert repo.rows["wh2"].host is None


def test_register_from_env_refuses_a_datasource_whose_secret_is_missing() -> None:
    with pytest.raises(MissingDatasourceSecretError, match="GENQL_ABSENT_DSN"):
        _service(FakeDatasources()).register_from_env("wh2", "postgres", "GENQL_ABSENT_DSN", None)


def test_remove_delegates_to_the_repository() -> None:
    repo = FakeDatasources()
    service = _service(repo)
    service.register("wh2", "postgres", CONNECTION, None)

    service.remove("wh2")

    assert repo.rows == {}


def test_remove_drops_the_cached_engine_for_that_datasource() -> None:
    """Otherwise this process keeps a pooled connection to a warehouse it no
    longer knows about, and re-adding the name reuses the stale one."""
    repo = FakeDatasources()
    engines = FakeEngines()
    service = _service(repo, engines)
    service.register("wh2", "postgres", CONNECTION, None)

    service.remove("wh2")

    assert engines.invalidated == ["wh2"]


def test_a_refused_removal_leaves_the_engine_cache_alone() -> None:
    engines = FakeEngines()

    with pytest.raises(UnknownDatasourceError):
        _service(FakeDatasources(), engines).remove("absent")

    assert engines.invalidated == []
