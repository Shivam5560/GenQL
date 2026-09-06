"""`genql query` — the first command that produces an answer rather than
metadata about one.

Every typed failure from the graph is caught here and printed as one line
with exit code 1, matching `genql discover`'s convention. The graph itself
never catches: a stage failure is a typed error all the way up, and this is
the only layer that knows it is talking to a human.
"""

from __future__ import annotations

import typer

from genql.api.query_graph import run_query
from genql.api.query_state import QueryState
from genql.composition_root import Container
from genql.domain.errors import GenqlError


def _render(final: QueryState) -> None:
    plan = final["plan"]
    if plan is not None:
        typer.echo("Plan:")
        typer.echo(plan.plan_text)
        typer.echo("")

    typer.echo("SQL:")
    typer.echo(final["validated_sql"] or "")
    typer.echo("")

    result = final["result"]
    if result is None:
        typer.echo("no rows returned")
        return
    typer.echo(" | ".join(result.columns))
    for row in result.rows:
        typer.echo(" | ".join("" if value is None else str(value) for value in row))
    typer.echo(f"({result.row_count} rows)")
    if result.truncated:
        typer.echo("truncated at the configured row cap; refine the question for the full set")


def query(
    question: str = typer.Argument(..., help="The analytical question, in English"),
    datasource: str = typer.Option(..., "--datasource", help="Registered datasource"),
    domain_id: int | None = typer.Option(None, "--domain-id", help="Restrict to one domain"),
) -> None:
    """Plan, generate, statically validate, and safely execute SQL for a question."""
    try:
        final = run_query(Container().query_graph(), question, datasource, domain_id)
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    _render(final)
