"""`genql datasource` — register, list, and remove warehouses.

Both ways of naming a warehouse are here. `--host/--port/--database/--user`
matches what the web connect form sends and stores the password encrypted;
`--dsn-env` names an environment variable the server already has set, which is
how every datasource registered before Phase 9 works and how a deployment that
would rather keep credentials out of the store entirely still can.

Domain errors are caught here and turned into a message plus exit code 1. A
traceback is the wrong thing to show someone who mistyped a hostname.
"""

from __future__ import annotations

import os

import typer

from genql.cli.commands import datasource_edit
from genql.composition_root import Container
from genql.domain.errors import GenqlError
from genql.domain.value_objects.datasource_connection import DatasourceConnection
from genql.registries.errors import RegistryError

app = typer.Typer(help="Register and inspect datasources")

# Attached rather than defined here: editing a registered datasource is its own
# command with its own option semantics, and this file is already the long one.
app.command("update")(datasource_edit.update)
app.command("dialects")(datasource_edit.dialects)

_PASSWORD_ENV = "GENQL_WAREHOUSE_PASSWORD"


def _connection(  # noqa: PLR0913, PLR0917 - one per connection field
    host: str,
    port: int,
    database: str,
    user: str,
    password: str | None,
    options: str | None,
) -> DatasourceConnection:
    """Prompts for the password rather than taking it as an option.

    An option would put the warehouse password in the shell history file and
    in the process table of every user on the machine. `$GENQL_WAREHOUSE_PASSWORD`
    is the non-interactive escape hatch for scripts.
    """
    if password is None:
        password = os.environ.get(_PASSWORD_ENV) or typer.prompt(
            "Warehouse password", hide_input=True, default="", show_default=False
        )
    return DatasourceConnection(
        host=host,
        port=port,
        database=database,
        username=user,
        password=password,
        options=options,
    )


@app.command("add")
def add(  # noqa: PLR0913, PLR0917 - one CLI option each
    name: str = typer.Option(..., "--name", help="Unique datasource name"),
    dialect: str = typer.Option("postgres", "--dialect", help="Registered SQL dialect"),
    host: str | None = typer.Option(None, "--host", help="Warehouse hostname"),
    port: int = typer.Option(5432, "--port"),
    database: str | None = typer.Option(None, "--database"),
    user: str | None = typer.Option(None, "--user", help="Role to connect as"),
    password: str | None = typer.Option(
        None, "--password", help=f"Prompted for if omitted; or set ${_PASSWORD_ENV}"
    ),
    options: str | None = typer.Option(
        None, "--options", help="Driver options, e.g. sslmode=require"
    ),
    dsn_env: str | None = typer.Option(
        None, "--dsn-env", help="Env var holding a whole DSN, instead of --host/--database"
    ),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Register a datasource, by endpoint or by environment variable."""
    service = Container().datasource_service()
    try:
        if dsn_env:
            created = service.register_from_env(name, dialect, dsn_env, description)
            target = f"${created.dsn_env_var}"
        else:
            if not (host and database and user):
                typer.echo("pass --host, --database and --user, or --dsn-env")
                raise typer.Exit(code=1)
            created = service.register(
                name,
                dialect,
                _connection(host, port, database, user, password, options),
                description,
            )
            target = created.endpoint or ""
    except (GenqlError, RegistryError) as exc:
        typer.echo(str(exc), err=False)
        raise typer.Exit(code=1) from exc
    typer.echo(f"registered {created.name} ({created.dialect}) -> {target}")


@app.command("list")
def list_datasources(
    enabled_only: bool = typer.Option(False, "--enabled-only"),
) -> None:
    """List registered datasources."""
    for datasource in Container().datasource_service().list_all(enabled_only=enabled_only):
        state = "enabled" if datasource.enabled else "disabled"
        target = datasource.endpoint or f"${datasource.dsn_env_var}"
        typer.echo(f"{datasource.name}\t{datasource.dialect}\t{target}\t{state}")


@app.command("remove")
def remove(name: str = typer.Option(..., "--name")) -> None:
    """Remove a datasource and, by cascade, everything discovered from it."""
    try:
        Container().datasource_service().remove(name)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"removed {name}")


@app.command("onboard")
def onboard(  # noqa: PLR0913, PLR0917 - one CLI option each
    name: str = typer.Option(..., "--name", help="Unique datasource name"),
    dialect: str = typer.Option("postgres", "--dialect"),
    host: str = typer.Option(..., "--host", help="Warehouse hostname"),
    port: int = typer.Option(5432, "--port"),
    database: str = typer.Option(..., "--database"),
    user: str = typer.Option(..., "--user", help="Role to connect as"),
    password: str | None = typer.Option(
        None, "--password", help=f"Prompted for if omitted; or set ${_PASSWORD_ENV}"
    ),
    options: str | None = typer.Option(None, "--options"),
    schema: list[str] = typer.Option([], "--schema", help="Schema to ingest; repeatable"),
    description: str | None = typer.Option(None, "--description"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Run the queued job here"),
) -> None:
    """Register a datasource and run the whole pipeline in one command.

    The same six stages the API queues — schemas, discovery, overlay, compile,
    graph analysis, domains — instead of six commands in the right order.
    `--no-wait` leaves the job on the queue for a running API's worker.
    """
    container = Container()
    try:
        _datasource, job = container.onboarding_service().register_and_submit(
            name,
            dialect,
            _connection(host, port, database, user, password, options),
            description,
            list(schema),
            user_id="cli",
        )
    except (GenqlError, RegistryError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"registered {name} ({dialect}); ingestion job {job.job_id} queued")
    if not wait:
        return

    # Drains the very job just queued: the worker claims whatever is oldest,
    # and this process is the only one running if no API is up.
    container.ingestion_worker().run_once()
    final = container.onboarding_service().status(name)
    for step in final.steps:
        marker = "ok  " if step.status.value in ("succeeded", "skipped") else "FAIL"
        typer.echo(f"  {marker} {step.name}: {step.detail or step.status.value}")
    if final.status.value != "succeeded":
        typer.echo(final.error or "ingestion failed")
        raise typer.Exit(code=1)
    typer.echo(f"{name} is ready to query")
