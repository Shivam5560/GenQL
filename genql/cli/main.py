"""GenQL command line."""

from __future__ import annotations

import typer

from genql.composition_root import Container
from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.ports.discovery_step import DiscoveryContext

app = typer.Typer(help="GenQL — enterprise NL2SQL with semantic enrichment")


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
    schema: str = typer.Option(..., "--schema", help="Warehouse schema to discover"),
    datasource: str = typer.Option("local", "--datasource", help="Registered datasource"),
    start_from: str | None = typer.Option(None, "--start-from", help="Resume from this step"),
) -> None:
    """Run the offline discovery pipeline."""
    container = Container()
    runner = container.discovery_runner()
    ctx = DiscoveryContext(
        datasource_name=datasource,
        schema_name=schema,
        sample_limit=container.settings().profile_sample_limit,
    )

    failed = False
    for result in runner.run(ctx, start_from=start_from):
        marker = "ok  " if result.succeeded else "FAIL"
        typer.echo(f"{marker} {result.step_name}: {result.message}")
        failed = failed or not result.succeeded

    raise typer.Exit(code=1 if failed else 0)


if __name__ == "__main__":
    app()
