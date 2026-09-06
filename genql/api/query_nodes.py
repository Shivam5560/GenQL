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

from genql.api.query_state import QueryState
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import ExecutionError, GenerationError, StaticValidationError
from genql.domain.ports.candidate_generator import CandidateGenerator
from genql.domain.ports.planner import Planner
from genql.domain.ports.schema_linker import SchemaLinker
from genql.services.query.guarded_execution_service import GuardedExecutionService
from genql.services.query.static_validation_service import StaticValidationService


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
        candidate = self._generator.generate(plan, state["links"] or (), violations)
        return {
            "candidate": candidate,
            # Counted here, not in the validation node: this is the attempt
            # being retried, so this is where "retry" becomes true.
            "retry_count": state["retry_count"] + (1 if violations else 0),
        }


class StaticValidationNode:
    def __init__(self, service: StaticValidationService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidate = state["candidate"]
        if candidate is None:
            raise StaticValidationError(
                (
                    GuardrailViolation(
                        rule_name="graph",
                        message="static validation was reached without a candidate",
                    ),
                )
            )
        try:
            validated = self._service.validate(candidate, state["datasource_name"])
        except StaticValidationError as exc:
            return {"validated_sql": None, "violations": exc.violations}
        return {"validated_sql": validated, "violations": ()}


class GuardedExecutionNode:
    def __init__(self, service: GuardedExecutionService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        sql = state["validated_sql"]
        if sql is None:
            raise ExecutionError("guarded execution was reached without validated SQL")
        return {"result": self._service.execute(sql, state["datasource_name"])}
