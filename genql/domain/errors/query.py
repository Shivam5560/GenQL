"""Failures raised by the online query pipeline (schema linking through
execution, optimization, ambiguity handling, and thread resumption)."""

from __future__ import annotations

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors.base import GenqlError


class QueryError(GenqlError):
    """The online query pipeline could not produce an answer.

    Runs online, not during discovery, so it hangs off GenqlError rather than
    DiscoveryError — same placement rule RetrievalError follows.
    """


class SchemaLinkingError(QueryError):
    """Retrieval returned nothing usable for this question."""


class PlanningError(QueryError):
    """The planner could not produce a valid QueryPlan."""


class GenerationError(QueryError):
    """The candidate generator could not produce a valid SqlCandidate."""


class StaticValidationError(QueryError):
    """A candidate failed one or more guardrails and could not be repaired.

    Carries the violations rather than only a message so the graph's retry
    edge can hand them back to candidate generation as feedback.
    """

    def __init__(self, violations: tuple[GuardrailViolation, ...]) -> None:
        detail = "; ".join(f"{v.rule_name}: {v.message}" for v in violations) or "no detail"
        super().__init__(f"static validation failed: {detail}")
        self.violations = violations


class ExecutionError(QueryError):
    """Guarded execution failed — timeout, permission denied, or a bad statement."""


class IntentClassificationError(QueryError):
    """The classifier returned something that is not a known question intent."""


class AmbiguityGateError(QueryError):
    """The ambiguity gate could not score the question's dimensions."""


class DomainScopingError(QueryError):
    """Domain scoping could not run at all.

    Distinct from "no domain resolved", which is a plain None return: this
    means the retrieval pass or the domain lookup itself failed, and the turn
    cannot continue with a silently unscoped search.
    """


class ThreadLockError(QueryError):
    """The per-thread advisory lock could not be acquired or released."""


class CritiqueError(QueryError):
    """Every surviving candidate carries a fatal defect, and the one escalated
    regeneration this phase allows has already been spent."""


class UnknownThreadError(QueryError):
    """`--thread-id` named a thread with no pending clarification to resume.

    Distinct from every checkpointed-but-wrong-answer case: this is what a
    thread id that was never checkpointed, already finished, or expired looks
    like from `resume_query`'s side, before the graph is invoked at all.
    """

    def __init__(self, thread_id: str) -> None:
        super().__init__(
            f"{thread_id!r} has no paused turn to resume: it is unknown, already "
            "finished, or its checkpoint has expired"
        )
        self.thread_id = thread_id


class OptimizationError(QueryError):
    """The rewrite-and-cost-gate stage could not reach a verdict.

    Not raised for an over-budget query — that is a normal, typed outcome.
    """


class CostEstimationError(QueryError):
    """EXPLAIN itself failed against the warehouse."""
