"""One property dominates: the run always completes. A paused turn, a
short-circuited intent, an over-budget narrowing, a raised error, and a
truncated reference are each a failed case with a named reason — never an
exception that costs the other forty-nine cases their run."""

from __future__ import annotations

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.errors import SchemaLinkingError
from genql.services.eval.golden_evaluation_service import GoldenEvaluationService
from genql.services.eval.result_comparator import ResultComparator

CASE = GoldenCase(
    case_id="c1",
    question="how many customers",
    datasource_name="local",
    reference_sql="SELECT count(*) FROM tpcds.customer",
    failure_class="ambiguous_intent",
)
EXPECTED = ExecutionResult(columns=("n",), rows=((100,),), row_count=1, truncated=False)
OTHER = ExecutionResult(columns=("n",), rows=((7,),), row_count=1, truncated=False)
TRUNCATED = ExecutionResult(columns=("n",), rows=((100,),), row_count=1, truncated=True)


class _Execution:
    def __init__(self, result: ExecutionResult = EXPECTED) -> None:
        self.result = result
        self.calls: list[str] = []

    def execute(self, sql: str, datasource_name: str) -> ExecutionResult:
        self.calls.append(sql)
        return self.result


class _Runner:
    def __init__(self, response: TurnResponse) -> None:
        self.response = response

    def run(self, question, datasource_name, domain_id=None):  # type: ignore[no-untyped-def]
        return self.response


class _RaisingRunner:
    def run(self, question, datasource_name, domain_id=None):  # type: ignore[no-untyped-def]
        raise SchemaLinkingError("no catalogued object matched")


def _service(execution: _Execution) -> GoldenEvaluationService:
    return GoldenEvaluationService(execution=execution, comparator=ResultComparator())


def _finished(result: ExecutionResult) -> TurnResponse:
    return TurnResponse(thread_id="t-1", validated_sql="SELECT count(*) FROM c", result=result)


def test_a_matching_result_passes() -> None:
    report = _service(_Execution()).run("full", (CASE,), _Runner(_finished(EXPECTED)))

    assert report.ablation_name == "full"
    assert report.outcomes[0].passed is True
    assert report.outcomes[0].generated_sql == "SELECT count(*) FROM c"


def test_a_differing_result_fails_with_a_reason() -> None:
    report = _service(_Execution()).run("full", (CASE,), _Runner(_finished(OTHER)))

    assert report.outcomes[0].passed is False
    assert "mismatch" in (report.outcomes[0].failure_reason or "")


def test_a_paused_turn_fails_with_a_named_reason_rather_than_hanging() -> None:
    paused = TurnResponse(thread_id="t-1", clarifying_question="which quarter?")

    report = _service(_Execution()).run("full", (CASE,), _Runner(paused))

    assert report.outcomes[0].passed is False
    assert "clarification" in (report.outcomes[0].failure_reason or "")


def test_a_short_circuited_intent_fails_with_a_named_reason() -> None:
    other = TurnResponse(thread_id="t-1", intent="non_sql")

    report = _service(_Execution()).run("full", (CASE,), _Runner(other))

    assert report.outcomes[0].passed is False
    assert "non_sql" in (report.outcomes[0].failure_reason or "")


def test_an_over_budget_turn_fails_with_the_narrowing_suggestion() -> None:
    over = TurnResponse(
        thread_id="t-1", validated_sql="SELECT 1", narrowing_suggestion="too expensive"
    )

    report = _service(_Execution()).run("full", (CASE,), _Runner(over))

    assert report.outcomes[0].passed is False
    assert "budget" in (report.outcomes[0].failure_reason or "").lower()


def test_a_raising_turn_fails_with_the_errors_text_and_the_run_completes() -> None:
    report = _service(_Execution()).run("full", (CASE, CASE), _RaisingRunner())

    assert len(report.outcomes) == 2
    assert all(o.passed is False for o in report.outcomes)
    assert "no catalogued object matched" in (report.outcomes[0].failure_reason or "")


def test_a_truncated_reference_is_a_fixture_error_not_a_verdict() -> None:
    report = _service(_Execution(TRUNCATED)).run("full", (CASE,), _Runner(_finished(EXPECTED)))

    assert report.outcomes[0].passed is False
    assert "row cap" in (report.outcomes[0].failure_reason or "")


def test_every_outcome_carries_its_cases_failure_class() -> None:
    report = _service(_Execution()).run("full", (CASE,), _Runner(_finished(EXPECTED)))

    assert report.outcomes[0].failure_class == "ambiguous_intent"


def test_an_empty_case_set_produces_an_empty_report_rather_than_raising() -> None:
    report = _service(_Execution()).run("full", (), _Runner(_finished(EXPECTED)))

    assert report.outcomes == ()
    assert report.accuracy == 0.0
