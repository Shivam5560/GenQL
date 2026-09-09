"""`genql optimizer` — the operator-facing half of Phase 7.

The parent spec's §11 is explicit that GenQL never creates an index itself, so
this command prints and exits. The empty-state message names both reasons the
list can be empty, because on a fresh installation the operator has no way to
tell "nothing to recommend" from "nothing was ever recorded".

Domain errors are caught here and turned into a message plus exit code 1, same
rule as every other command. An unregistered `--datasource` is one of them: the
service refuses the name rather than reporting it empty.
"""

from __future__ import annotations

import psycopg
import typer

from genql.composition_root import Container
from genql.domain.errors import GenqlError

app = typer.Typer(help="Inspect and act on the optimizer's accumulated evidence")


@app.command("recommend-indexes")
def recommend_indexes(
    datasource: str = typer.Option(..., "--datasource", help="Registered datasource"),
) -> None:
    """Print indexes worth creating, ranked by how much evidence supports them."""
    try:
        container = Container()
        recommendations = container.index_recommendation_service().recommend(datasource)
    except (GenqlError, ValueError, psycopg.Error) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    if not recommendations:
        typer.echo(
            "no recommendations yet — either record_execution_actuals is off, or no "
            "executions have been recorded for this datasource"
        )
        return

    typer.echo("object | column | executions | rationale")
    for recommendation in recommendations:
        typer.echo(
            f"{recommendation.object_qualified_name} | {recommendation.column_name} | "
            f"{recommendation.supporting_execution_count} | {recommendation.rationale}"
        )
