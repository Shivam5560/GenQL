"""GenQL command line."""

from __future__ import annotations

import typer

from genql.cli.commands import datasource as datasource_commands
from genql.cli.commands import graph as graph_commands
from genql.cli.commands import optimizer as optimizer_commands
from genql.cli.commands import query as query_commands
from genql.cli.commands import schema as schema_commands
from genql.cli.commands import semantic as semantic_commands
from genql.composition_root import Container
from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.errors import GenqlError

app = typer.Typer(help="GenQL — enterprise NL2SQL with semantic enrichment")
app.add_typer(datasource_commands.app, name="datasource")
app.add_typer(graph_commands.app, name="graph")
app.add_typer(optimizer_commands.app, name="optimizer")
app.add_typer(schema_commands.app, name="schema")
app.add_typer(semantic_commands.app, name="semantic")
# `query` is a top-level command, not a sub-app: `genql query "..."` reads
# better than `genql query run "..."`, and there is nothing else under it.
app.command("query")(query_commands.query)


@app.command()
def steps() -> None:
    """List registered discovery steps."""
    # SIM118 is a false positive here: DISCOVERY_STEPS is a Registry, not a
    # dict, and `.keys()` is its own method (no __iter__), so `ruff --fix`'s
    # suggested `for name in DISCOVERY_STEPS:` would raise TypeError.
    for name in DISCOVERY_STEPS.keys():  # noqa: SIM118
        typer.echo(name)


@app.command()
def discover(
    datasource: str | None = typer.Option(None, "--datasource", help="Registered datasource"),
    schema: list[str] = typer.Option([], "--schema", help="Registered schema; repeatable"),
    start_from: str | None = typer.Option(None, "--start-from", help="Resume from this step"),
) -> None:
    """Run the offline discovery pipeline over the resolved scope."""
    container = Container()
    # Both calls are inside the guard: an unresolvable scope and an unknown
    # --start-from are both the caller's mistake, and neither deserves a
    # traceback. Per-schema failures never land here — run_scope reports those
    # as failed outcomes below.
    try:
        scope = container.scope_resolver().resolve(datasource, schema)
        outcomes = container.discovery_runner().run_scope(
            scope,
            sample_limit=container.settings().profile_sample_limit,
            start_from=start_from,
        )
    except GenqlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    failed = False
    for outcome in outcomes:
        typer.echo(outcome.ref.qualified_name)
        for result in outcome.results:
            marker = "ok  " if result.succeeded else "FAIL"
            typer.echo(f"  {marker} {result.step_name}: {result.message}")
        failed = failed or not outcome.succeeded

    raise typer.Exit(code=1 if failed else 0)


if __name__ == "__main__":
    app()
