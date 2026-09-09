"""`genql eval` — the two mechanisms the parent spec's §15 substitutes for
public benchmarks.

Every accuracy is printed with its counts. Six cases is not a measurement, and
a bare `0.83` reads like one; `0.83 (5/6)` does not. The ablate command also
names the layer it cannot measure, so an absent row is never mistaken for a
measured zero.
"""

from __future__ import annotations

import psycopg
import typer

from genql.composition_root import Container
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.errors import GenqlError
from genql.domain.value_objects.failure_class import FAILURE_CLASSES

app = typer.Typer(help="Run the golden set and the ablation harness")

_UNMEASURED = (
    "not measured: query log — offline query-log mining is not implemented in this "
    "build, so there is no layer to switch off"
)


def _render_cases(report: GoldenRunReport) -> None:
    for outcome in report.outcomes:
        marker = "ok  " if outcome.passed else "FAIL"
        typer.echo(f"  {marker} {outcome.case_id} ({outcome.elapsed_ms:.0f} ms)")
        if not outcome.passed and outcome.failure_reason:
            typer.echo(f"       {outcome.failure_reason}")


def _render_accuracy(report: GoldenRunReport) -> None:
    total = len(report.outcomes)
    typer.echo(f"accuracy: {report.accuracy:.2f} ({report.passed_count}/{total})")
    for failure_class in FAILURE_CLASSES:
        passed, count = report.counts_for(failure_class)
        if count:
            typer.echo(f"  {failure_class}: {passed / count:.2f} ({passed}/{count})")


@app.command("golden")
def golden(
    datasource: str = typer.Option(..., "--datasource", help="Registered datasource"),
    report_path: str | None = typer.Option(None, "--report", help="Write a JSON report here"),
    failure_class: str | None = typer.Option(
        None, "--failure-class", help="Run only cases of this failure class"
    ),
) -> None:
    """Run every curated case and compare execution results."""
    try:
        # record_execution_actuals is on for evaluation runs so that
        # `genql optimizer recommend-indexes` has evidence on a fresh install.
        container = Container.with_overrides(record_execution_actuals=True)
        cases = container.golden_set_reader().read_cases(datasource)
        if failure_class is not None:
            cases = tuple(c for c in cases if c.failure_class == failure_class)
        result = container.golden_evaluation_service().run("full", cases, container.turn_runner())
        if report_path is not None:
            container.report_writer().write(report_path, (result,))
    except (GenqlError, ValueError, psycopg.Error) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    _render_cases(result)
    typer.echo("")
    _render_accuracy(result)


@app.command("ablate")
def ablate(
    datasource: str = typer.Option(..., "--datasource", help="Registered datasource"),
    ablation: list[str] = typer.Option(
        [], "--ablation", help="Ablation to run; repeatable. Default: all registered."
    ),
    report_path: str | None = typer.Option(None, "--report", help="Write a JSON report here"),
) -> None:
    """Run the golden set once per ablation and print each delta from the baseline."""
    try:
        container = Container()
        cases = container.golden_set_reader().read_cases(datasource)
        reports = container.ablation_service().run(tuple(ablation), cases)
        if report_path is not None:
            container.report_writer().write(report_path, reports)
    except (GenqlError, ValueError, psycopg.Error) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    baseline = next((r.accuracy for r in reports if r.ablation_name == "full"), None)
    typer.echo("ablation | accuracy | delta")
    for report in reports:
        total = len(report.outcomes)
        delta = "—" if baseline is None else f"{report.accuracy - baseline:+.2f}"
        typer.echo(
            f"{report.ablation_name} | {report.accuracy:.2f} "
            f"({report.passed_count}/{total}) | {delta}"
        )
    typer.echo("")
    typer.echo(_UNMEASURED)
    typer.echo(
        "an ablation measures a layer's absence, not its quality: it says what happens "
        "with none of that layer, not what better input would buy"
    )
