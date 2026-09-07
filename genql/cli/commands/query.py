"""`genql query` — one turn of the online pipeline.

Three outcomes, three renderings, two exit codes. A finished turn prints its
SQL and rows; a paused turn prints its clarifying question plus the thread id
to resume with; a question the system does not answer prints why. Only a typed
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
    if not response.applied_defaults:
        return
    # "Resolved", not "applied": the rule's value is recorded here but is not
    # yet threaded into PlanningService/CandidateGenerationService's prompts,
    # so saying it was "applied" would overclaim what actually reached the SQL.
    typer.echo("Resolved via rule (not yet applied to generation):")
    for dimension, rule_name in response.applied_defaults:
        typer.echo(f"  {dimension} -> {rule_name}")
    typer.echo("")


def _render_paused(response: TurnResponse) -> None:
    typer.echo(response.clarifying_question or "")
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


def _render_finished(response: TurnResponse) -> None:
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
    typer.echo(f"thread: {response.thread_id}")


def _render(response: TurnResponse) -> None:
    if response.clarifying_question is not None:
        _render_paused(response)
    elif response.intent is not None:
        _render_intent(response)
    else:
        _render_finished(response)


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

    _render(response)
