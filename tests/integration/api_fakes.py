"""Shared fakes for the HTTP-route and SSE-stream tests.

AUTH is the header every request needs: the routes verify a bearer token, and
FakeVerifier accepts any, so a transport test says `headers=AUTH` and moves on.

Built by hand rather than by overriding a real container: the real container
opens a checkpointer pool on first resolution, and these tests must not need
a database.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from genql.domain.value_objects.authenticated_user import AuthenticatedUser


class _Locks:
    @contextmanager
    def for_thread(self, thread_id: str) -> Iterator[None]:
        yield


class FakeSettings:
    """Only what create_app itself reads.

    Empty CORS origins install no middleware, and tracing stays off — these
    tests assert on transport, and a collector nobody is running is not part
    of it.
    """

    cors_allowed_origins = ""
    tracing_enabled = False
    tracing_endpoint = ""
    tracing_project = "test"


class FakeVerifier:
    """Accepts any bearer token: these tests are not about token validation."""

    def verify(self, token: str) -> AuthenticatedUser:
        return AuthenticatedUser(user_id="u-test", email="dev@example.com")


class FakeContainer:
    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def token_verifier(self) -> FakeVerifier:
        return FakeVerifier()

    def settings(self) -> FakeSettings:
        return FakeSettings()

    def query_graph(self) -> Any:
        return self._graph

    def thread_lock_factory(self) -> _Locks:
        return _Locks()


class _State:
    def __init__(self, interrupts: tuple[Any, ...]) -> None:
        self.interrupts = interrupts


class FakeGraph:
    """`invoke` returns (or raises) a fixed payload; `stream` yields fixed chunks."""

    def __init__(self, raw: Any = None, chunks: list[dict[str, Any]] | None = None) -> None:
        self._raw = raw
        self._chunks = chunks or []

    def invoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        if isinstance(self._raw, Exception):
            raise self._raw
        return {**state, **(self._raw or {})}

    def stream(
        self, state: Any, config: dict[str, Any], stream_mode: str
    ) -> Iterator[dict[str, Any]]:
        for chunk in self._chunks:
            for delta in chunk.values():
                if isinstance(delta, Exception):
                    raise delta
            yield chunk

    def get_state(self, config: dict[str, Any]) -> _State:
        return _State(interrupts=())


#: What every authenticated request in these tests sends.
AUTH = {"Authorization": "Bearer test-token"}
