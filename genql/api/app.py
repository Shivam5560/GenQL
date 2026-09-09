"""The FastAPI application.

Endpoints are synchronous `def`, so FastAPI runs each on a worker thread. The
whole pipeline below is synchronous — SQLAlchemy, psycopg, httpx, neo4j — and
making the transport async would not make any of it concurrent; it would only
move the blocking off the loop by rewriting every layer.

All error translation happens here, in one handler, so no controller contains a
`try`. UnknownDatasourceError and UnknownThreadError are 404 because the client
named something that does not exist; every other GenqlError is 400 because the
request could not be served as asked; anything else is a bug and is 500.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from genql.api.controllers import (
    datasource_controller,
    feedback_controller,
    query_controller,
    stream_controller,
)
from genql.domain.errors import GenqlError, UnknownDatasourceError, UnknownThreadError

_NOT_FOUND = (UnknownDatasourceError, UnknownThreadError)


def create_app(container: Any) -> FastAPI:
    app = FastAPI(title="GenQL", version="0.1.0")
    app.state.container = container

    @app.exception_handler(GenqlError)
    def _handle_genql_error(request: Request, exc: GenqlError) -> JSONResponse:
        status = 404 if isinstance(exc, _NOT_FOUND) else 400
        return JSONResponse(
            status_code=status,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(query_controller.router, prefix="/v1")
    app.include_router(stream_controller.router, prefix="/v1")
    app.include_router(feedback_controller.router, prefix="/v1")
    app.include_router(datasource_controller.router, prefix="/v1")
    return app
