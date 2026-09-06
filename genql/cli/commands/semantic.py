"""`genql semantic` — merge YAML overrides, compile the search index, and
query it. Domain errors are caught here and turned into a message plus exit
code 1, same rule as every other command."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from genql.composition_root import Container
from genql.domain.entities.semantic_overlay import SemanticOverlay
from genql.domain.errors import GenqlError

app = typer.Typer(help="Merge YAML overrides, compile, and search the semantic store")


@app.command("overlay")
def overlay(datasource: str = typer.Option(..., "--datasource")) -> None:
    """Validate and merge semantic/<datasource>.yaml over discovered/LLM enrichment."""
    path = Path("semantic") / f"{datasource}.yaml"
    if not path.exists():
        typer.echo(f"no overlay file at {path}; nothing to apply")
        return
    try:
        parsed = SemanticOverlay.model_validate(yaml.safe_load(path.read_text()))
    except ValidationError as exc:
        typer.echo(f"{path} failed validation:\n{exc}")
        raise typer.Exit(code=1) from exc
    try:
        report = Container().semantic_overlay_service().apply(parsed)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"{report.objects_updated} objects, {report.columns_updated} columns, "
        f"{report.metrics_written} metrics, {report.join_hints_written} join hints"
    )


@app.command("compile")
def compile_command(
    datasource: str = typer.Option(..., "--datasource"),
    write_back: bool = typer.Option(False, "--write-back", help="Also COMMENT ON the warehouse"),
) -> None:
    """Build genql_search_document; optionally write descriptions back to the warehouse."""
    try:
        report = Container().compile_service().compile(datasource, write_back=write_back)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"{report.documents} documents compiled, {report.comments_written} comments written")


@app.command("search")
def search(
    datasource: str = typer.Option(..., "--datasource"),
    question: str = typer.Argument(...),
    top_k: int = typer.Option(10, "--top-k"),
    domain_id: int | None = typer.Option(None, "--domain-id"),
) -> None:
    """Hybrid retrieval plus reranking — the first command that answers
    something resembling the product question."""
    try:
        results = Container().retrieval_service().search(datasource, question, top_k, domain_id)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    for r in results:
        typer.echo(f"{r.schema_name}.{r.object_name}  domain={r.domain_name}  score={r.score:.4f}")
