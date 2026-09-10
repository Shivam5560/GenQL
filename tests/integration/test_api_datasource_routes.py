"""The datasource management routes: edit, remove, and what dialects exist.

Against a fake container, so these assert transport — status codes, the shape
of the body, and the one thing that must never appear in it — rather than
persistence, which the repository tests cover.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi.testclient import TestClient

from genql.api.app import create_app
from genql.domain.entities.datasource import Datasource
from genql.domain.errors import UnknownDatasourceError
from genql.domain.value_objects.authenticated_user import AuthenticatedUser
from genql.domain.value_objects.datasource_update import DatasourceUpdate

AUTH = {"Authorization": "Bearer token"}

WH = Datasource(
    name="wh",
    dialect="postgres",
    host="old.internal",
    port=5432,
    database="analytics",
    username="reader",
    password_ciphertext="terces",
)


class FakeVerifier:
    def verify(self, token: str) -> AuthenticatedUser:
        return AuthenticatedUser(user_id="u-1", email="dev@example.com")


class FakeDatasourceService:
    def __init__(self, row: Datasource | None = WH) -> None:
        self.row = row
        self.updated: tuple[str, DatasourceUpdate] | None = None
        self.removed: list[str] = []

    def update(self, name: str, patch: DatasourceUpdate) -> Datasource:
        if self.row is None:
            raise UnknownDatasourceError(name, [])
        self.updated = (name, patch)
        self.row = self.row.model_copy(update=patch.changes())
        return self.row

    def remove(self, name: str) -> None:
        if self.row is None:
            raise UnknownDatasourceError(name, [])
        self.removed.append(name)

    def dialects(self) -> Sequence[str]:
        return ["postgres"]


class FakeSettings:
    #: Empty, so create_app installs no CORS middleware for these tests.
    cors_allowed_origins = ""


class FakeContainer:
    def __init__(self, service: FakeDatasourceService) -> None:
        self._service = service

    def settings(self) -> FakeSettings:
        return FakeSettings()

    def token_verifier(self) -> FakeVerifier:
        return FakeVerifier()

    def datasource_service(self) -> FakeDatasourceService:
        return self._service


def _client(service: FakeDatasourceService) -> TestClient:
    return TestClient(create_app(FakeContainer(service)), raise_server_exceptions=False)


def test_patching_a_datasource_returns_the_edited_row() -> None:
    response = _client(FakeDatasourceService()).patch(
        "/v1/datasources/wh", json={"host": "new.internal", "port": 6543}, headers=AUTH
    )

    assert response.status_code == 200
    assert response.json()["endpoint"] == "new.internal:6543/analytics"


def test_patching_passes_only_the_mentioned_fields_to_the_service() -> None:
    service = FakeDatasourceService()

    _client(service).patch("/v1/datasources/wh", json={"description": "prod"}, headers=AUTH)

    assert service.updated is not None
    assert service.updated[1].changes() == {"description": "prod"}


def test_a_patched_datasource_never_carries_a_password_back() -> None:
    response = _client(FakeDatasourceService()).patch(
        "/v1/datasources/wh", json={"password": "n3w"}, headers=AUTH
    )

    assert response.status_code == 200
    assert "password" not in response.json()
    assert "password_ciphertext" not in response.json()


def test_patching_an_unknown_datasource_is_404() -> None:
    response = _client(FakeDatasourceService(row=None)).patch(
        "/v1/datasources/nope", json={"host": "h"}, headers=AUTH
    )

    assert response.status_code == 404
    assert response.json()["error"] == "UnknownDatasourceError"


def test_patching_without_a_token_is_401() -> None:
    response = _client(FakeDatasourceService()).patch("/v1/datasources/wh", json={"host": "h"})

    assert response.status_code == 401


def test_deleting_a_datasource_is_204() -> None:
    service = FakeDatasourceService()

    response = _client(service).delete("/v1/datasources/wh", headers=AUTH)

    assert response.status_code == 204
    assert service.removed == ["wh"]


def test_deleting_an_unknown_datasource_is_404() -> None:
    response = _client(FakeDatasourceService(row=None)).delete("/v1/datasources/nope", headers=AUTH)

    assert response.status_code == 404


def test_the_dialects_route_answers_from_the_registry() -> None:
    response = _client(FakeDatasourceService()).get("/v1/datasources/dialects", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"dialects": ["postgres"]}
