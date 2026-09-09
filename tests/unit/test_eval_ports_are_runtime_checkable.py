"""Every port is a runtime_checkable Protocol, matching every port since
Phase 1. The check is cheap and catches the one mistake that is otherwise
invisible until composition: a Protocol declared without the decorator, which
makes `isinstance` raise rather than answer."""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.domain.entities.feedback import Feedback
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.ports.feedback_writer import FeedbackWriter
from genql.domain.ports.golden_set_reader import GoldenSetReader
from genql.domain.ports.report_writer import ReportWriter
from genql.domain.ports.search_document_recompiler import SearchDocumentRecompiler
from genql.domain.ports.turn_runner import TurnRunner
from genql.domain.ports.turn_runner_factory import TurnRunnerFactory


class _GoldenSetReader:
    def read_cases(self, datasource_name: str | None = None) -> tuple[GoldenCase, ...]:
        return ()


class _TurnRunner:
    def run(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> TurnResponse:
        return TurnResponse(thread_id="t-1")


class _TurnRunnerFactory:
    def for_ablation(self, ablation: Ablation) -> TurnRunner:
        return _TurnRunner()


class _SearchDocumentRecompiler:
    def recompile(self, ablation: Ablation, datasource_name: str) -> int:
        return 0


class _FeedbackWriter:
    def write(self, feedback: Feedback) -> None:
        return None


class _ReportWriter:
    def write(self, path: str, reports: tuple[GoldenRunReport, ...]) -> None:
        return None


def test_every_eval_port_is_runtime_checkable() -> None:
    assert isinstance(_GoldenSetReader(), GoldenSetReader)
    assert isinstance(_TurnRunner(), TurnRunner)
    assert isinstance(_TurnRunnerFactory(), TurnRunnerFactory)
    assert isinstance(_SearchDocumentRecompiler(), SearchDocumentRecompiler)
    assert isinstance(_FeedbackWriter(), FeedbackWriter)
    assert isinstance(_ReportWriter(), ReportWriter)
