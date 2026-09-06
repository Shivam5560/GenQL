"""`genql datasource` — register, list, and remove warehouses.

Domain errors are caught here and turned into a message plus exit code 1. A
traceback is the wrong thing to show someone who mistyped an environment
variable name.
"""

from __future__ import annotations

import typer

from genql.composition_root import Container
from genql.domain.errors import GenqlError
from genql.registries.errors import RegistryError

app = typer.Typer(help="Register and inspect datasources")


@app.command("add")
def add(
    name: str = typer.Option(..., "--name", help="Unique datasource name"),
    dialect: str = typer.Option("postgres", "--dialect", help="Registered SQL dialect"),
    dsn_env: str = typer.Option(
        ..., "--dsn-env", help="Name of the environment variable holding the DSN"
    ),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Register a datasource. The DSN itself is never stored."""
    service = Container().datasource_service()
    try:
        created = service.register(name, dialect, dsn_env, description)
    except (GenqlError, RegistryError) as exc:
        typer.echo(str(exc), err=False)
        raise typer.Exit(code=1) from exc
    typer.echo(f"registered {created.name} ({created.dialect}) -> ${created.dsn_env_var}")


@app.command("list")
def list_datasources(
    enabled_only: bool = typer.Option(False, "--enabled-only"),
) -> None:
    """List registered datasources."""
    for datasource in Container().datasource_service().list_all(enabled_only=enabled_only):
        state = "enabled" if datasource.enabled else "disabled"
        typer.echo(f"{datasource.name}\t{datasource.dialect}\t{datasource.dsn_env_var}\t{state}")


@app.command("remove")
def remove(name: str = typer.Option(..., "--name")) -> None:
    """Remove a datasource and, by cascade, everything discovered from it."""
    try:
        Container().datasource_service().remove(name)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"removed {name}")
