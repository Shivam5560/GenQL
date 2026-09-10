"""Editing a registered datasource, the counterpart to registering one.

Update validates as eagerly as registration does — an unknown dialect, an
unset environment variable, or a half-filled endpoint is refused here rather
than surfacing as a connection failure during the next discovery run. The
password is the only field that cannot be read back, so "leave it alone" and
"replace it" have to be distinguishable without the caller ever seeing it.
"""

from __future__ import annotations

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import (
    IncompleteDatasourceConnectionError,
    MissingDatasourceSecretError,
    UnknownDatasourceError,
)
from genql.domain.value_objects.datasource_update import DatasourceUpdate
from genql.registries.errors import UnknownRegistryKeyError
from tests.unit.test_datasource_service import (
    FakeDatasources,
    FakeEngines,
    _service,
)

ENDPOINT = Datasource(
    name="wh",
    dialect="postgres",
    host="old.internal",
    port=5432,
    database="analytics",
    username="reader",
    password_ciphertext="terces",
    description="before",
)

BY_ENV = Datasource(name="wh", dialect="postgres", dsn_env_var="GENQL_WH2_DSN")


def _repo(datasource: Datasource) -> FakeDatasources:
    repo = FakeDatasources()
    repo.add(datasource)
    return repo


def test_update_moves_the_endpoint() -> None:
    repo = _repo(ENDPOINT)

    updated = _service(repo).update("wh", DatasourceUpdate(host="new.internal", port=6543))

    assert updated.host == "new.internal"
    assert updated.port == 6543
    assert repo.rows["wh"].host == "new.internal"


def test_update_encrypts_a_replacement_password() -> None:
    updated = _service(_repo(ENDPOINT)).update("wh", DatasourceUpdate(password="n3w"))

    assert updated.password_ciphertext == "w3n"


def test_update_without_a_password_keeps_the_stored_one() -> None:
    updated = _service(_repo(ENDPOINT)).update("wh", DatasourceUpdate(host="new.internal"))

    assert updated.password_ciphertext == "terces"


def test_an_empty_password_clears_the_stored_one() -> None:
    updated = _service(_repo(ENDPOINT)).update("wh", DatasourceUpdate(password=""))

    assert updated.password_ciphertext is None


def test_update_leaves_unmentioned_fields_alone() -> None:
    updated = _service(_repo(ENDPOINT)).update("wh", DatasourceUpdate(host="new.internal"))

    assert updated.description == "before"
    assert updated.username == "reader"
    assert updated.enabled is True


def test_update_can_disable_a_datasource() -> None:
    updated = _service(_repo(ENDPOINT)).update("wh", DatasourceUpdate(enabled=False))

    assert updated.enabled is False


def test_update_invalidates_the_pooled_engine() -> None:
    engines = FakeEngines()

    _service(_repo(ENDPOINT), engines).update("wh", DatasourceUpdate(host="new.internal"))

    assert engines.invalidated == ["wh"]


def test_a_refused_update_leaves_the_pooled_engine_alone() -> None:
    engines = FakeEngines()

    with pytest.raises(UnknownRegistryKeyError):
        _service(_repo(ENDPOINT), engines).update("wh", DatasourceUpdate(dialect="oracle"))

    assert engines.invalidated == []


def test_update_rejects_an_unknown_dialect() -> None:
    with pytest.raises(UnknownRegistryKeyError, match="oracle"):
        _service(_repo(ENDPOINT)).update("wh", DatasourceUpdate(dialect="oracle"))


def test_update_of_an_unknown_datasource_raises() -> None:
    with pytest.raises(UnknownDatasourceError):
        _service(_repo(ENDPOINT)).update("missing", DatasourceUpdate(host="new.internal"))


def test_moving_to_stored_credentials_clears_the_dsn_env_var() -> None:
    updated = _service(_repo(BY_ENV)).update(
        "wh",
        DatasourceUpdate(
            host="new.internal", port=5432, database="analytics", username="reader", password="p"
        ),
    )

    assert updated.dsn_env_var is None
    assert updated.endpoint == "new.internal:5432/analytics"


def test_moving_to_a_dsn_env_var_clears_the_stored_credentials() -> None:
    updated = _service(_repo(ENDPOINT)).update("wh", DatasourceUpdate(dsn_env_var="GENQL_WH2_DSN"))

    assert updated.dsn_env_var == "GENQL_WH2_DSN"
    assert updated.host is None
    assert updated.password_ciphertext is None
    assert updated.endpoint is None


def test_update_rejects_a_dsn_env_var_that_is_not_set() -> None:
    with pytest.raises(MissingDatasourceSecretError):
        _service(_repo(ENDPOINT)).update("wh", DatasourceUpdate(dsn_env_var="GENQL_NOT_SET"))


def test_a_host_without_a_database_is_refused() -> None:
    with pytest.raises(IncompleteDatasourceConnectionError, match="database"):
        _service(_repo(BY_ENV)).update("wh", DatasourceUpdate(host="new.internal"))
