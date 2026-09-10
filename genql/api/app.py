"""The FastAPI application.

Endpoints are synchronous `def`, so FastAPI runs each on a worker thread. The
whole pipeline below is synchronous — SQLAlchemy, psycopg, httpx, neo4j — and
making the transport async would not make any of it concurrent; it would only
move the blocking off the loop by rewriting every layer.

All error translation happens here, in one handler, so no controller contains a
`try`. Naming something that does not exist is 404; a well-formed request that
collides with state already there — a duplicate datasource, an ingestion
already running — is 409, so a client can tell "retry later" from "fix this";
every other GenqlError is 400 because the request could not be served as
asked; anything else is a bug and is 500.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from genql.api.controllers import (
    datasource_controller,
    feedback_controller,
    profile_controller,
    query_controller,
    stream_controller,
    threads_controller,
)
from genql.domain.errors import (
    DuplicateDatasourceError,
    GenqlError,
    IngestionInProgressError,
    InvalidAccessTokenError,
    NoIngestionJobError,
    ThreadOwnershipError,
    UnknownDatasourceError,
    UnknownIngestionJobError,
    UnknownThreadError,
)
from genql.infrastructure.tracing.tracer import configure_tracing

_NOT_FOUND = (
    UnknownDatasourceError,
    UnknownThreadError,
    ThreadOwnershipError,
    UnknownIngestionJobError,
    NoIngestionJobError,
)
_UNAUTHORIZED = (InvalidAccessTokenError,)
# 409, not 400: the request was well-formed and would succeed later. A client
# that cannot tell those apart retries a malformed request forever, or gives
# up on a queue that was merely busy.
_CONFLICT = (DuplicateDatasourceError, IngestionInProgressError)


def create_app(container: Any) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Own the ingestion worker's lifetime.

        Started here rather than at import time so a test app, the CLI, and
        anything else building a container do not silently acquire a thread
        that claims jobs out from under the process that meant to run them.
        """
        worker = container.ingestion_worker()
        worker.start()
        # Started here rather than at import time for the same reason, and
        # shut down explicitly so the last batch of spans is flushed instead
        # of dying with the process.
        settings = container.settings()
        tracer = configure_tracing(
            enabled=settings.tracing_enabled,
            endpoint=settings.tracing_endpoint,
            project=settings.tracing_project,
        )
        try:
            yield
        finally:
            worker.stop()
            if tracer is not None:
                tracer.shutdown()

    app = FastAPI(title="GenQL", version="0.1.0", lifespan=lifespan)
    app.state.container = container

    settings = container.settings()
    origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(GenqlError)
    def _handle_genql_error(request: Request, exc: GenqlError) -> JSONResponse:
        status = (
            404
            if isinstance(exc, _NOT_FOUND)
            else 401
            if isinstance(exc, _UNAUTHORIZED)
            else 409
            if isinstance(exc, _CONFLICT)
            else 400
        )
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
    app.include_router(threads_controller.router, prefix="/v1")
    app.include_router(profile_controller.router, prefix="/v1")
    return app
