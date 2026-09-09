"""The routes against a container whose graph is a fake, so the assertions are
about transport — status codes, shapes, error mapping — and not about the
pipeline, which every other test already covers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from genql.api.app import create_app
from genql.domain.errors import SchemaLinkingError, UnknownDatasourceError, UnknownThreadError
from tests.integration.api_fakes import FakeContainer, FakeGraph

FINISHED = {
    "validated_sql": "SELECT 1",
    "result": None,
    "intent": "analytical_sql",
    "optimization": None,
}


def _client(raw: object) -> TestClient:
    return TestClient(create_app(FakeContainer(FakeGraph(raw=raw))), raise_server_exceptions=False)


def test_healthz_is_ok() -> None:
    assert _client(FINISHED).get("/healthz").json() == {"status": "ok"}


def test_starting_a_turn_returns_the_dto() -> None:
    response = _client(FINISHED).post(
        "/v1/queries", json={"question": "how many customers", "datasource": "local"}
    )

    assert response.status_code == 200
    assert response.json()["validated_sql"] == "SELECT 1"
    assert response.json()["thread_id"]


def test_a_request_missing_a_required_field_is_422() -> None:
    assert _client(FINISHED).post("/v1/queries", json={"question": "q"}).status_code == 422


def test_an_unknown_datasource_is_404() -> None:
    client = _client(UnknownDatasourceError("nope", ["local"]))

    response = client.post("/v1/queries", json={"question": "q", "datasource": "nope"})

    assert response.status_code == 404
    assert response.json()["error"] == "UnknownDatasourceError"


def test_an_unknown_thread_is_404() -> None:
    client = _client(UnknownThreadError("t-missing"))

    response = client.post("/v1/queries/t-missing/resume", json={"answer": "q3"})

    assert response.status_code == 404


def test_any_other_typed_failure_is_400_with_its_type_name() -> None:
    client = _client(SchemaLinkingError("no catalogued object matched"))

    response = client.post("/v1/queries", json={"question": "q", "datasource": "local"})

    assert response.status_code == 400
    assert response.json()["error"] == "SchemaLinkingError"
    assert "no catalogued object" in response.json()["detail"]
