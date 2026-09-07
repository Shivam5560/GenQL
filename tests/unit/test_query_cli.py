"""`genql query`'s three jobs: render a finished turn, render a paused one, and
turn any typed failure into one line plus exit code 1 rather than a traceback.

The container, the graph, and the turn functions are all stubbed — this asserts
the command's presentation and its error boundary, not the pipeline, which the
node, graph, and turn tests already cover.

A paused turn exits 0. That is the single most important assertion in this
file: a clarifying question is the system working, and a non-zero exit would
make every shell caller treat it as breakage.
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

import genql.cli.commands.query as query_command
from genql.cli.main import app
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.errors import ExecutionError, SchemaLinkingError

runner = CliRunner()


class StubContainer:
    def query_graph(self) -> object:
        return object()

    def thread_lock_factory(self) -> object:
        return object()


def _install(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> dict[str, Any]:
    """Stubs both turn entry points and records which one was called."""
    monkeypatch.setattr(query_command, "Container", StubContainer)
    seen: dict[str, Any] = {}

    def fake_start(  # noqa: PLR0913, PLR0917 - matches start_turn's signature
        graph: Any,
        locks: Any,
        question: str,
        datasource_name: str,
        domain_id: int | None = None,
        thread_id: str | None = None,
    ) -> TurnResponse:
        seen["call"] = "start"
        seen["args"] = (question, datasource_name, domain_id, thread_id)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def fake_resume(graph: Any, locks: Any, answer: str, thread_id: str) -> TurnResponse:
        seen["call"] = "resume"
        seen["args"] = (answer, thread_id)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(query_command, "start_turn", fake_start)
    monkeypatch.setattr(query_command, "resume_turn", fake_resume)
    return seen


def finished(truncated: bool = False) -> TurnResponse:
    return TurnResponse(
        thread_id="t-1",
        validated_sql="SELECT count(*) FROM shop.orders LIMIT 1",
        result=ExecutionResult(
            columns=("count", "note"), rows=((7, None),), row_count=1, truncated=truncated
        ),
        applied_defaults=(("time_range", "default_period"),),
    )


def test_a_finished_turn_prints_the_sql_and_the_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, finished())

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert result.exit_code == 0
    assert "SELECT count(*) FROM shop.orders LIMIT 1" in result.stdout
    assert "count | note" in result.stdout
    assert "7 |" in result.stdout
    assert "(1 rows)" in result.stdout


def test_a_finished_turn_reports_the_defaults_it_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A default the user did not ask for must be visible, or the answer is
    silently about a different question than the one they asked."""
    _install(monkeypatch, finished())

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert "time_range" in result.stdout
    assert "default_period" in result.stdout


def test_the_defaults_wording_does_not_overclaim_that_the_value_was_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule's value is recorded, never threaded into generation — the
    wording must not say it was "applied", which would overclaim."""
    _install(monkeypatch, finished())

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert "Applied defaults:" not in result.stdout
    assert "not yet applied" in result.stdout


def test_a_truncated_result_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, finished(truncated=True))

    result = runner.invoke(app, ["query", "q", "--datasource", "local"])

    assert "truncated" in result.stdout


def test_a_paused_turn_prints_the_question_the_thread_id_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        TurnResponse(thread_id="t-abc", clarifying_question="Over what time period?"),
    )

    result = runner.invoke(app, ["query", "show me revenue", "--datasource", "local"])

    assert result.exit_code == 0
    assert "Over what time period?" in result.stdout
    assert "t-abc" in result.stdout
    assert "--thread-id" in result.stdout


def test_a_non_analytical_question_is_explained_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, TurnResponse(thread_id="t-1", intent="non_sql"))

    result = runner.invoke(app, ["query", "hello there", "--datasource", "local"])

    assert result.exit_code == 0
    assert "non_sql" in result.stdout


def test_a_thread_id_routes_to_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install(monkeypatch, finished())

    runner.invoke(app, ["query", "last quarter", "--datasource", "local", "--thread-id", "t-abc"])

    assert seen["call"] == "resume"
    assert seen["args"] == ("last quarter", "t-abc")


def test_no_thread_id_routes_to_start_with_the_domain_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _install(monkeypatch, finished())

    runner.invoke(app, ["query", "how many orders", "--datasource", "local", "--domain-id", "42"])

    assert seen["call"] == "start"
    assert seen["args"] == ("how many orders", "local", 42, None)


def test_a_typed_failure_is_one_line_and_exit_code_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, SchemaLinkingError("nothing matched"))

    result = runner.invoke(app, ["query", "q", "--datasource", "local"])

    assert result.exit_code == 1
    assert "nothing matched" in result.stdout
    assert "Traceback" not in result.stdout
    assert len(result.stdout.strip().splitlines()) == 1


def test_a_failure_during_resume_is_also_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, ExecutionError("statement timeout"))

    result = runner.invoke(
        app, ["query", "last quarter", "--datasource", "local", "--thread-id", "t-abc"]
    )

    assert result.exit_code == 1
    assert "statement timeout" in result.stdout


def test_a_resume_with_no_datasource_flag_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact command the CLI itself prints as a resume hint carries no
    --datasource — following it must actually work, not fail with a missing
    required option."""
    seen = _install(monkeypatch, finished())

    result = runner.invoke(app, ["query", "last quarter", "--thread-id", "t-abc"])

    assert result.exit_code == 0, result.stdout
    assert seen["call"] == "resume"
    assert seen["args"] == ("last quarter", "t-abc")


def test_a_fresh_query_with_no_datasource_and_no_thread_id_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, finished())

    result = runner.invoke(app, ["query", "how many orders"])

    assert result.exit_code != 0
    assert "datasource" in result.output
    assert "required" in result.output
