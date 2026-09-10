from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import DuplicateDatasourceError, UnknownDatasourceError
from genql.repositories.semantic.datasource_repository import PostgresDatasourceRepository

WH2 = Datasource(
    name="repo_wh2", dialect="postgres", dsn_env_var="GENQL_WH2_DSN", description="second"
)
DISABLED = Datasource(
    name="repo_off", dialect="postgres", dsn_env_var="GENQL_OFF_DSN", enabled=False
)


@pytest.fixture()
def repo(migrated_engine: Engine) -> PostgresDatasourceRepository:
    with migrated_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM genql.genql_datasource WHERE name IN ('repo_wh2', 'repo_off')")
        )
    return PostgresDatasourceRepository(engine=migrated_engine)


def test_add_then_get_round_trips(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)
    assert repo.get("repo_wh2") == WH2


def test_add_twice_raises_duplicate(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)
    with pytest.raises(DuplicateDatasourceError):
        repo.add(WH2)


def test_get_unknown_raises_and_names_the_alternatives(
    repo: PostgresDatasourceRepository,
) -> None:
    repo.add(WH2)
    with pytest.raises(UnknownDatasourceError, match="repo_wh2"):
        repo.get("nope")


def test_list_all_can_filter_to_enabled(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)
    repo.add(DISABLED)

    names = {d.name for d in repo.list_all(enabled_only=True)}

    assert "repo_wh2" in names
    assert "repo_off" not in names


def test_remove_deletes_the_row(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)
    repo.remove("repo_wh2")
    with pytest.raises(UnknownDatasourceError):
        repo.get("repo_wh2")


def test_remove_unknown_raises(repo: PostgresDatasourceRepository) -> None:
    with pytest.raises(UnknownDatasourceError):
        repo.remove("never_existed")


def test_update_writes_the_edited_row(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)

    repo.update(WH2.model_copy(update={"description": "edited", "enabled": False}))

    stored = repo.get("repo_wh2")
    assert stored.description == "edited"
    assert stored.enabled is False


def test_update_of_an_unknown_datasource_raises(repo: PostgresDatasourceRepository) -> None:
    repo.add(WH2)

    with pytest.raises(UnknownDatasourceError, match="repo_wh2"):
        repo.update(WH2.model_copy(update={"name": "ghost"}))
