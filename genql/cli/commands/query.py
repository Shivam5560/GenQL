"""`genql query` — one turn of the online pipeline.

Four outcomes, four renderings, two exit codes. A finished turn prints its
SQL and rows; a paused turn prints its clarifying question plus the thread id
to resume with; a question the system does not answer prints why; a query the
cost gate refused prints the statement it declined to run and how to narrow
it. Only a typed
failure exits non-zero — a paused turn is the system working, and a non-zero
exit would make every shell caller treat a clarifying question as breakage.

Every typed failure from the graph is caught here and printed as one line,
matching `genql discover`'s convention. The graph itself never catches: a stage
failure is a typed error all the way up, and this is the only layer that knows
it is talking to a human.
"""

from __future__ import annotations

import psycopg
import typer

from genql.api.query_turn import resume_turn, start_turn
from genql.composition_root import Container
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.errors import GenqlError


def _render_defaults(response: TurnResponse) -> None:
    """Which rules fired, and what was decided without asking.

    These print as two blocks because they answer two different questions.
    `applied_defaults` names the RULE, which is what someone who disagrees
    needs in order to go edit it; `assumed` states the VALUE that actually
    reached the plan, which is what someone checking the answer needs. The
    two overlap but are not the same list: an assumption can come from the
    question budget rather than from any rule.

    "Applied", not "resolved", is now accurate: PlanningNode states these to
    the planner as binding and the plan is what binds generation, so unlike
    when this function was written the value genuinely does reach the SQL.
    """
    if response.applied_defaults:
        typer.echo("Applied rules:")
        for dimension, rule_name in response.applied_defaults:
            typer.echo(f"  {dimension} -> {rule_name}")
        typer.echo("")
    if response.assumed:
        typer.echo("Assumed without asking (say so in a follow-up to change one):")
        for dimension, value in response.assumed:
            typer.echo(f"  {dimension}: {value}")
        typer.echo("")


def _render_paused(response: TurnResponse) -> None:
    typer.echo(response.clarifying_question or "")
    if response.suggested_answer:
        typer.echo(f"  suggested: {response.suggested_answer}")
    for option in response.clarification_options:
        typer.echo(f"  or: {option}")
    typer.echo("")
    _render_defaults(response)
    typer.echo(f"thread: {response.thread_id}")
    typer.echo(f'Answer with: genql query "<answer>" --thread-id {response.thread_id}')


def _render_intent(response: TurnResponse) -> None:
    typer.echo(
        f"This looks like a {response.intent} question, not an analytical one. "
        "GenQL answers questions about the data in a registered warehouse; ask "
        "for numbers, totals, or rows and it will generate SQL for them."
    )
    typer.echo(f"thread: {response.thread_id}")


def _render_provenance(response: TurnResponse) -> None:
    """How the answer was reached, printed only under --verbose.

    Provenance is for someone auditing an answer. Printing it on every turn
    would bury the answer itself under the reasoning that produced it.
    """
    typer.echo("")
    typer.echo("Provenance:")
    typer.echo(f"  plan: {response.plan_text or '(none)'}")
    typer.echo(f"  referenced objects: {', '.join(response.referenced_objects) or '(none)'}")
    typer.echo(f"  candidates: {response.candidate_count}, probes: {response.probe_count}")
    if response.selection_method is not None:
        typer.echo(f"  selected by {response.selection_method}: {response.selection_rationale}")


def _render_finished(response: TurnResponse, *, verbose: bool = False) -> None:
    _render_defaults(response)
    typer.echo("SQL:")
    typer.echo(response.validated_sql or "")
    typer.echo("")

    result = response.result
    if result is None:
        typer.echo("no rows returned")
    else:
        typer.echo(" | ".join(result.columns))
        for row in result.rows:
            typer.echo(" | ".join("" if value is None else str(value) for value in row))
        typer.echo(f"({result.row_count} rows)")
        if result.truncated:
            typer.echo("truncated at the configured row cap; refine the question for the full set")
    if response.rewrite_rules_applied:
        typer.echo(f"rewrites applied: {', '.join(response.rewrite_rules_applied)}")
    if verbose:
        _render_provenance(response)
    typer.echo(f"thread: {response.thread_id}")


def _render_over_budget(response: TurnResponse) -> None:
    typer.echo("SQL (not executed):")
    typer.echo(response.validated_sql or "")
    typer.echo("")
    typer.echo(response.narrowing_suggestion or "")
    typer.echo(f"thread: {response.thread_id}")


def _render(response: TurnResponse, *, verbose: bool = False) -> None:
    if response.clarifying_question is not None:
        _render_paused(response)
    elif response.narrowing_suggestion is not None:
        _render_over_budget(response)
    elif response.intent is not None:
        _render_intent(response)
    else:
        _render_finished(response, verbose=verbose)


def query(
    question: str = typer.Argument(
        ..., help="The analytical question, or the answer to a clarifying question"
    ),
    datasource: str | None = typer.Option(
        None,
        "--datasource",
        help="Registered datasource. Required to start a new turn; omit it when "
        "resuming with --thread-id — the checkpointed state already has it.",
    ),
    domain_id: int | None = typer.Option(None, "--domain-id", help="Restrict to one domain"),
    thread_id: str | None = typer.Option(
        None, "--thread-id", help="Resume a paused turn instead of starting a new one"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Print the plan, referenced objects, candidate/probe counts, and "
        "selection rationale beneath the SQL",
    ),
) -> None:
    """Answer a question, or ask one back when the question is under-specified."""
    if thread_id is None and datasource is None:
        raise typer.BadParameter(
            "--datasource is required to start a new query "
            "(omit it only when resuming with --thread-id)",
            param_hint="--datasource",
        )
    try:
        # Resolving query_graph transitively builds the checkpointer, which
        # opens a real connection pool and runs PostgresSaver.setup() — a bad
        # DSN or a down database raises here, so this must be inside the try.
        container = Container()
        graph = container.query_graph()
        locks = container.thread_lock_factory()
        if thread_id is not None:
            response = resume_turn(graph, locks, question, thread_id)
        else:
            assert datasource is not None  # guaranteed by the check above
            response = start_turn(graph, locks, question, datasource, domain_id)
    except (GenqlError, ValueError, psycopg.Error) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    _render(response, verbose=verbose)
