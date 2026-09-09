"""The graph's shared state.

`violations` rather than a rendered message: the router needs the failure to
decide, the regeneration node needs it as feedback, and the CLI needs it in
the error it prints — a tuple of entities serves all three, a string serves
none of them well.

`clarifications` is what makes the interrupt loop terminate. Each pause
appends one (dimension, answer) pair, and the gate treats an answered
dimension as resolved, so the set of dimensions it can still ask about
strictly shrinks toward empty. It is also, literally, the parent spec's §13
"structured state, not appended chat text": what persists is which dimension
was settled and how, not a transcript.

`thread_id` is required rather than optional: every turn has one, including a
turn that finishes without pausing, because a follow-up question needs
something to attach to.
"""

from __future__ import annotations

from typing import TypedDict

from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.optimization_result import OptimizationResult
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


class QueryState(TypedDict):
    question: str
    datasource_name: str
    thread_id: str
    domain_id: int | None
    intent: str | None
    ambiguity: AmbiguityAssessment | None
    clarifications: tuple[tuple[str, str], ...]
    links: tuple[SchemaLink, ...] | None
    plan: QueryPlan | None
    # Phase 5/6's single `candidate` becomes a tuple: the non-contested path
    # is now the len(candidates) == 1 case, not a structurally different
    # type. No compatibility shim — every caller updates in this task.
    candidates: tuple[SqlCandidate, ...]
    # Index-aligned with `candidates` after static validation drops the
    # failures: candidates[i]'s qualified SQL is validated_sqls[i]. Critique,
    # probing, and selection read and write against this field —
    # SqlCandidate.sql stays the pre-repair, pre-qualification text.
    validated_sqls: tuple[str, ...]
    # Whether clarifications or applied_defaults were non-empty when the
    # ambiguity gate last cleared — the sole gate for every new stage this
    # phase adds, per the parent spec's demand-driven mandate.
    contested: bool
    critique_reports: tuple[CritiqueReport, ...]
    probe_results: tuple[ProbeResult, ...]
    selection: CandidateSelection | None
    # Whether the one escalated regeneration this phase allows has already
    # been spent — by static validation exhausting its own retry, or by
    # critique finding every survivor fatal, whichever happens first.
    escalated: bool
    # What the rewrite-and-cost-gate stage decided. None until that node runs;
    # the router reads `within_budget` from it, and query_turn reads
    # `narrowing_suggestion` and `rules_applied` for the response.
    optimization: OptimizationResult | None
    validated_sql: str | None
    result: ExecutionResult | None
    retry_count: int
    violations: tuple[GuardrailViolation, ...]


def initial_state(
    question: str,
    datasource_name: str,
    thread_id: str,
    domain_id: int | None = None,
) -> QueryState:
    return QueryState(
        question=question,
        datasource_name=datasource_name,
        thread_id=thread_id,
        domain_id=domain_id,
        intent=None,
        ambiguity=None,
        clarifications=(),
        links=None,
        plan=None,
        candidates=(),
        validated_sqls=(),
        contested=False,
        critique_reports=(),
        probe_results=(),
        selection=None,
        escalated=False,
        optimization=None,
        validated_sql=None,
        result=None,
        retry_count=0,
        violations=(),
    )
