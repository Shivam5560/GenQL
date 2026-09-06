"""`genql graph` — run community detection, embeddings, and join-path mining,
and rebuild the projection from Postgres alone.

Domain errors are caught here and turned into a message plus exit code 1,
same rule as every other command.
"""

from __future__ import annotations

import typer

from genql.composition_root import Container
from genql.domain.errors import GenqlError
from genql.domain.value_objects.schema_ref import SchemaRef

app = typer.Typer(help="Project, analyze, and rebuild the graph")


@app.command("analyze")
def analyze(datasource: str = typer.Option(..., "--datasource")) -> None:
    """Run Leiden, FastRP, and join-path mining over one datasource's graph."""
    try:
        report = Container().graph_analysis_service().analyze(datasource)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"{report.communities} communities, {report.embedded_nodes} nodes embedded, "
        f"{report.join_paths} join paths"
    )


@app.command("rebuild")
def rebuild(datasource: str = typer.Option(..., "--datasource")) -> None:
    """Re-project every enabled schema of a datasource from Postgres alone."""
    container = Container()
    try:
        registrations = container.schema_registration_repository().list_for_datasource(
            datasource, enabled_only=True
        )
        service = container.graph_projection_service()
        for registration in registrations:
            ref = SchemaRef(datasource_name=datasource, schema_name=registration.schema_name)
            report = service.project(ref)
            typer.echo(f"{ref.qualified_name}: {report.objects} objects, {report.edges} edges")
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
