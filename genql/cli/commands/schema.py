"""`genql schema` — register, list, and remove managed schemas."""

from __future__ import annotations

import typer

from genql.composition_root import Container
from genql.domain.errors import GenqlError
from genql.domain.value_objects.schema_ref import SchemaRef

app = typer.Typer(help="Register and inspect schemas")


@app.command("add")
def add(
    datasource: str = typer.Option(..., "--datasource"),
    schema: str = typer.Option(..., "--schema"),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Register a schema after verifying it exists in the datasource."""
    ref = SchemaRef(datasource_name=datasource, schema_name=schema)
    try:
        Container().schema_registration_service().register(ref, description)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"registered {ref.qualified_name}")


@app.command("list")
def list_schemas(
    datasource: str | None = typer.Option(None, "--datasource"),
) -> None:
    """List registered schemas, for one datasource or all of them."""
    container = Container()
    names = (
        [datasource]
        if datasource is not None
        else [d.name for d in container.datasource_service().list_all()]
    )
    service = container.schema_registration_service()
    for name in names:
        for registration in service.list_for_datasource(name):
            state = "enabled" if registration.enabled else "disabled"
            discovered = registration.last_discovered_at or "never"
            typer.echo(f"{registration.ref.qualified_name}\t{state}\t{discovered}")


@app.command("remove")
def remove(
    datasource: str = typer.Option(..., "--datasource"),
    schema: str = typer.Option(..., "--schema"),
) -> None:
    """Remove a schema registration and, by cascade, its catalog rows."""
    ref = SchemaRef(datasource_name=datasource, schema_name=schema)
    try:
        Container().schema_registration_service().remove(ref)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"removed {ref.qualified_name}")
