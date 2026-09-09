"""`genql serve` — uvicorn over the app factory, one process.

Defaults bind 127.0.0.1: this is a development server for a single-user system,
and a default of 0.0.0.0 would expose an unauthenticated query API to the
network the first time someone ran it.
"""

from __future__ import annotations

import typer
import uvicorn

from genql.api.app import create_app
from genql.composition_root import Container


def serve(
    host: str | None = typer.Option(None, "--host", help="Bind address"),
    port: int | None = typer.Option(None, "--port", help="Bind port"),
) -> None:
    """Serve the GenQL HTTP API."""
    container = Container()
    settings = container.settings()
    uvicorn.run(
        create_app(container),
        host=host or settings.api_host,
        port=port or settings.api_port,
    )
