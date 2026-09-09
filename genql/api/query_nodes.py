"""Five adapters between QueryState and the five services.

Each one reads the fields it needs, calls its service, and returns only the
fields it changed. Nothing here decides anything: routing lives in
query_graph.py, and business logic lives in the services. The one exception is
StaticValidationNode, which converts its typed failure into state so the
router has something to route on — the failure is re-raised there, not
swallowed.

A node reached without the input it needs raises rather than returning a
half-filled state: that can only happen if the graph's edges are wrong, and a
wrong edge should fail at the first node it reaches.
"""

from __future__ import annotations

from typing import Any

import structlog

from genql.api.query_state import QueryState
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ExecutionError, GenerationError, StaticValidationError
from genql.domain.ports.candidate_generator import CandidateGenerator
from genql.domain.ports.planner import Planner
from genql.domain.ports.schema_linker import SchemaLinker
from genql.services.query.guarded_execution_service import GuardedExecutionService
from genql.services.query.rewrite_recording_service import RewriteOutcomeRecordingService
from genql.services.query.static_validation_service import StaticValidationService

_log = structlog.get_logger(__name__)


class SchemaLinkingNode:
    def __init__(self, linker: SchemaLinker) -> None:
        self._linker = linker

    def __call__(self, state: QueryState) -> dict[str, Any]:
        links = self._linker.link(state["question"], state["datasource_name"], state["domain_id"])
        return {"links": links}


class PlanningNode:
    def __init__(self, planner: Planner) -> None:
        self._planner = planner

    def __call__(self, state: QueryState) -> dict[str, Any]:
        return {"plan": self._planner.plan(state["question"], state["links"] or ())}


class CandidateGenerationNode:
    def __init__(self, generator: CandidateGenerator) -> None:
        self._generator = generator

    def __call__(self, state: QueryState) -> dict[str, Any]:
        plan = state["plan"]
        if plan is None:
            raise GenerationError("candidate generation was reached without a plan")
        violations = state["violations"]
        candidates = self._generator.generate(
            plan,
            state["links"] or (),
            violations,
            domain_id=state["domain_id"],
            contested=state["contested"],
            escalated=state["escalated"],
        )
        return {
            "candidates": candidates,
            "retry_count": state["retry_count"] + (1 if violations else 0),
        }


class StaticValidationNode:
    """Validates every candidate independently, one repair attempt each,
    exactly Phase 5's per-candidate rule — collecting survivors rather than
    treating the batch as all-or-nothing.

    Raises directly (Deviation 1) rather than writing failure into state for
    the router to raise: granting the one escalated retry is a one-shot
    decision this node must make and act on in the same evaluation, using the
    `escalated` value it was handed. `not state["escalated"]` guards BOTH
    retry branches, so once the budget is spent (here or by CritiqueNode) no
    further regeneration is ever granted again, from either stage.
    """

    def __init__(self, service: StaticValidationService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidates = state["candidates"]
        if not candidates:
            raise StaticValidationError(
                (
                    GuardrailViolation(
                        rule_name="graph",
                        message="static validation was reached without any candidates",
                    ),
                )
            )

        survivors: list[SqlCandidate] = []
        validated_sqls: list[str] = []
        all_violations: list[GuardrailViolation] = []
        for candidate in candidates:
            try:
                validated = self._service.validate(candidate, state["datasource_name"])
            except StaticValidationError as exc:
                all_violations.extend(exc.violations)
                continue
            survivors.append(candidate)
            validated_sqls.append(validated)

        if survivors:
            return {
                "candidates": tuple(survivors),
                "validated_sqls": tuple(validated_sqls),
                "violations": (),
            }

        combined = tuple(all_violations)
        repairable = any(violation.repairable for violation in combined)
        if repairable and not state["escalated"] and state["retry_count"] == 0:
            return {"candidates": (), "validated_sqls": (), "violations": combined}
        if repairable and state["contested"] and not state["escalated"]:
            return {
                "candidates": (),
                "validated_sqls": (),
                "violations": combined,
                "escalated": True,
            }
        raise StaticValidationError(combined)


class GuardedExecutionNode:
    """Runs the statement, then — only when a recorder was constructed —
    measures it.

    The recorder is `None` whenever `Settings.record_execution_actuals` is
    false, because the composition root simply does not build one. That keeps
    the disabled path a single `is not None` check rather than a second
    conditional edge in the graph.

    The try/except is deliberately bare-`Exception`: the recording path runs
    EXPLAIN (ANALYZE, BUFFERS) against the warehouse and writes a row to
    GenQL's store, and *no* failure of a diagnostic may lose a turn whose
    query already returned rows to the user. It is logged rather than
    swallowed silently — ruff's SIM105 rejects a bare `pass` here, and a
    warning is the only way a broken recorder is ever noticed.
    """

    def __init__(
        self,
        service: GuardedExecutionService,
        recorder: RewriteOutcomeRecordingService | None = None,
    ) -> None:
        self._service = service
        self._recorder = recorder

    def __call__(self, state: QueryState) -> dict[str, Any]:
        sql = state["validated_sql"]
        if sql is None:
            raise ExecutionError("guarded execution was reached without validated SQL")
        result = self._service.execute(sql, state["datasource_name"])

        optimization = state["optimization"]
        if self._recorder is not None and optimization is not None:
            try:
                self._recorder.record(
                    sql,
                    optimization.rules_applied,
                    optimization.estimated_cost,
                    state["datasource_name"],
                )
            except Exception as exc:  # noqa: BLE001 - never fail a served turn
                _log.warning("optimizer.recording_failed", error=str(exc))

        return {"result": result}
