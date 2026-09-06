"""`genql query`'s two jobs: render a finished run, and turn any typed failure
into one line plus exit code 1 rather than a traceback.

The container and the graph are both stubbed — this asserts the command's
presentation and its error boundary, not the pipeline, which the node and
graph tests already cover.
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

import genql.cli.commands.query as query_command
from genql.api.query_state import QueryState, initial_state
from genql.cli.main import app
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.errors import ExecutionError, SchemaLinkingError, StaticValidationError

PLAN = QueryPlan(question="q", plan_text="count the orders", referenced_objects=("shop.orders",))
runner = CliRunner()


class StubContainer:
    def query_graph(self) -> object:
        return object()


def _install(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> None:
    monkeypatch.setattr(query_command, "Container", StubContainer)

    def fake_run_query(
        graph: Any, question: str, datasource_name: str, domain_id: int | None = None
    ) -> QueryState:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(query_command, "run_query", fake_run_query)


def _finished_state(truncated: bool = False) -> QueryState:
    state = initial_state("q", "local")
    state["plan"] = PLAN
    state["validated_sql"] = "SELECT count(*) FROM shop.orders LIMIT 1"
    state["result"] = ExecutionResult(
        columns=("count", "note"),
        rows=((7, None),),
        row_count=1,
        truncated=truncated,
    )
    return state


def test_it_prints_the_plan_the_sql_and_the_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _finished_state())

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert result.exit_code == 0
    assert "count the orders" in result.stdout
    assert "SELECT count(*) FROM shop.orders LIMIT 1" in result.stdout
    assert "count | note" in result.stdout
    assert "7 | " in result.stdout
    assert "(1 rows)" in result.stdout
    assert "truncated" not in result.stdout


def test_it_says_so_when_the_row_cap_truncated_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _finished_state(truncated=True))

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert result.exit_code == 0
    assert "truncated at the configured row cap" in result.stdout


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (SchemaLinkingError("no catalogued object matched 'q'"), "no catalogued object"),
        (
            StaticValidationError(
                (GuardrailViolation(rule_name="statement_kind", message="DELETE is not permitted"),)
            ),
            "DELETE is not permitted",
        ),
        (ExecutionError("statement timed out"), "statement timed out"),
    ],
)
def test_a_typed_failure_is_one_line_and_exit_code_one(
    monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    _install(monkeypatch, error)

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert result.exit_code == 1
    assert expected in result.stdout
    assert "Traceback" not in result.stdout
    assert len(result.stdout.strip().splitlines()) == 1


def test_the_domain_id_option_is_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(query_command, "Container", StubContainer)

    def fake_run_query(
        graph: Any, question: str, datasource_name: str, domain_id: int | None = None
    ) -> QueryState:
        seen["domain_id"] = domain_id
        seen["question"] = question
        seen["datasource_name"] = datasource_name
        return _finished_state()

    monkeypatch.setattr(query_command, "run_query", fake_run_query)

    result = runner.invoke(
        app, ["query", "how many orders", "--datasource", "local", "--domain-id", "3"]
    )

    assert result.exit_code == 0
    assert seen == {"domain_id": 3, "question": "how many orders", "datasource_name": "local"}
