"""`genql datasource update` — edit a registered datasource in place.

Its own module rather than another command in `datasource.py`: this is the
only command whose whole job is to distinguish "not mentioned" from "set to
nothing", and that distinction is what every option here is shaped around.
Omitting an option leaves the column alone; `--clear-options` and
`--clear-password` are how a column is emptied, spelled as flags because an
empty string on a command line is too easy to pass by accident.

The password is never an option value, for the same reason it is not one on
`datasource add`: it would land in the shell history and in the process table.
`--set-password` prompts for it, or reads $GENQL_WAREHOUSE_PASSWORD when there
is no terminal to prompt on.
"""

from __future__ import annotations

import os

import typer

from genql.composition_root import Container
from genql.domain.errors import GenqlError
from genql.domain.value_objects.datasource_update import DatasourceUpdate
from genql.registries.errors import RegistryError

_PASSWORD_ENV = "GENQL_WAREHOUSE_PASSWORD"


def _password(set_password: bool, clear_password: bool) -> str | None:
    """None leaves the stored password alone; "" is the instruction to forget it."""
    if clear_password:
        return ""
    if not set_password:
        return None
    return os.environ.get(_PASSWORD_ENV) or typer.prompt(
        "Warehouse password", hide_input=True, default="", show_default=False
    )


def update(  # noqa: PLR0913, PLR0917 - one CLI option each
    name: str = typer.Option(..., "--name", help="Registered datasource to edit"),
    dialect: str | None = typer.Option(None, "--dialect", help="Registered SQL dialect"),
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
    database: str | None = typer.Option(None, "--database"),
    user: str | None = typer.Option(None, "--user", help="Role to connect as"),
    set_password: bool = typer.Option(
        False, "--set-password", help=f"Prompt for a new password, or read ${_PASSWORD_ENV}"
    ),
    clear_password: bool = typer.Option(
        False, "--clear-password", help="Forget the stored password"
    ),
    options: str | None = typer.Option(None, "--options", help="Driver options"),
    clear_options: bool = typer.Option(False, "--clear-options"),
    dsn_env: str | None = typer.Option(
        None, "--dsn-env", help="Read the whole DSN from this environment variable instead"
    ),
    description: str | None = typer.Option(None, "--description"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
) -> None:
    """Change where a datasource points, or turn it off.

    The name is not editable: every catalog row, profile and ingestion job
    references a datasource by name, so renaming one would orphan all of them.
    """
    patch = DatasourceUpdate(
        dialect=dialect,
        dsn_env_var=dsn_env,
        host=host,
        port=port,
        database=database,
        username=user,
        password=_password(set_password, clear_password),
        options="" if clear_options else options,
        description=description,
        enabled=enabled,
    )
    try:
        edited = Container().datasource_service().update(name, patch)
    except (GenqlError, RegistryError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    target = edited.endpoint or f"${edited.dsn_env_var}"
    state = "enabled" if edited.enabled else "disabled"
    typer.echo(f"updated {edited.name} ({edited.dialect}) -> {target} [{state}]")


def dialects() -> None:
    """List the dialects a datasource may be registered with."""
    for dialect in Container().datasource_service().dialects():
        typer.echo(dialect)
