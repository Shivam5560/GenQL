"""What a stage puts beside its line, and the budget it has to do it in.

`detail` is one sentence for a narrow rail. `facts` is the same decision as
label/value pairs, so a reader renders "3 of 4 cleared, 1 repaired" as three
values rather than parsing it back out of prose. Four of these stages reported
nothing at all before — a stage that says nothing is indistinguishable from a
stage that did not run, and that ambiguity is the bug underneath the rail.
"""

from __future__ import annotations

from genql.api.sse.stage_events import to_stage_event
from genql.api.sse.stage_summary import MAX_FACT_VALUE, MAX_FACTS
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.optimization_result import OptimizationResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.entities.stage_event import StageEvent

PLAN = QueryPlan(question="q", plan_text="sum sales by month", referenced_objects=("local.a.b",))


def facts(event: StageEvent) -> dict[str, str]:
    return dict(event.facts)


# ── The four stages that used to report nothing ─────────────────────────────


def test_intent_classification_reports_the_intent_it_read() -> None:
    event = to_stage_event("intent_classification", {"intent": "analytical_sql"})

    assert event.status == "completed"
    assert facts(event)["intent"] == "analytical_sql"


def test_domain_scoping_reports_the_domain_it_chose() -> None:
    event = to_stage_event("domain_scoping", {"domain_id": 3})

    assert facts(event)["domain_id"] == "3"


def test_critique_reports_every_score_and_every_defect() -> None:
    reports = (
        CritiqueReport(candidate_index=0, defects=(), score=0.92),
        CritiqueReport(
            candidate_index=1,
            defects=(Defect(dimension="grain", severity="fatal", message="double counts"),),
            score=0.41,
        ),
    )

    event = to_stage_event("critique", {"critique_reports": reports})

    assert event.status == "completed"
    assert facts(event)["scores"] == "#0 0.92 · #1 0.41"
    assert "double counts" in facts(event)["defects"]
    assert facts(event)["fatal"] == "1"


def test_the_resumed_interrupt_node_reports_the_answer_it_took() -> None:
    event = to_stage_event(
        "ambiguity_interrupt", {"clarifications": (("metric", "credit status good"),)}
    )

    assert event.status == "completed"
    assert facts(event)["dimension"] == "metric"
    assert facts(event)["your answer"] == "credit status good"


# ── The stages that reported a count where a decision was wanted ────────────


def test_the_gate_reports_every_dimension_it_scored() -> None:
    assessment = AmbiguityAssessment(
        is_ambiguous=False,
        assumed=(("time_range", "all history"),),
        applied_defaults=(("time_range", "default_period"),),
        dimension_scores=(("entity", 0.96), ("metric", 0.31)),
    )

    event = to_stage_event("ambiguity_gate", {"ambiguity": assessment, "contested": True})

    assert facts(event)["confidence"] == "entity 0.96 · metric 0.31"
    assert facts(event)["assumed"] == "time_range=all history"
    assert facts(event)["rule defaults"] == "time_range via default_period"
    assert facts(event)["contested"] == "yes"


def test_static_validation_reports_the_guardrails_that_fired() -> None:
    violations = (GuardrailViolation(rule_name="row_limit", message="no LIMIT", repairable=True),)

    event = to_stage_event(
        "static_validation", {"validated_sqls": (), "violations": violations, "escalated": True}
    )

    assert facts(event)["cleared"] == "0"
    assert "row_limit: no LIMIT" in facts(event)["guardrails fired"]
    assert facts(event)["repairable"] == "yes"
    assert facts(event)["escalated"] == "yes"


def test_selection_carries_the_rationale_not_only_the_method() -> None:
    selection = CandidateSelection(
        selected=SqlCandidate(sql="SELECT 1", plan=PLAN),
        selected_sql="SELECT 1",
        method="probe_resolved",
        rationale="only candidate 2 predicted the real count",
    )

    event = to_stage_event("candidate_selection", {"selection": selection})

    assert facts(event)["method"] == "probe_resolved"
    assert facts(event)["why"] == "only candidate 2 predicted the real count"


def test_schema_linking_names_the_objects_behind_the_count() -> None:
    """ "9 objects linked" cannot answer "why this table and not that one".
    The names can, and they are already in the delta."""
    links = (
        SchemaLink(object_qualified_name="local.tpcds.store_sales", column_names=("ss_sk",)),
        SchemaLink(object_qualified_name="local.tpcds.customer", join_paths=("a->b",)),
    )

    event = to_stage_event("schema_linking", {"links": links})

    assert facts(event)["objects"] == "2"
    assert facts(event)["columns"] == "1"
    assert facts(event)["join paths"] == "1"
    assert "local.tpcds.store_sales" in facts(event)["linked"]


# ── The budget, and the envelope ────────────────────────────────────────────


def test_a_fact_value_is_capped_and_marked_where_it_was_cut() -> None:
    links = tuple(SchemaLink(object_qualified_name=f"local.schema.object_{i}") for i in range(200))

    event = to_stage_event("schema_linking", {"links": links})

    assert len(facts(event)["linked"]) <= MAX_FACT_VALUE
    assert facts(event)["linked"].endswith("…")
    assert len(event.facts) <= MAX_FACTS


def test_a_fact_with_no_value_is_dropped_rather_than_rendered_empty() -> None:
    """Most stages have facts that exist only on some paths — the narrowing
    suggestion, the guardrails that fired. Dropping an empty one centrally is
    what keeps every summariser from guarding each of its own."""
    cleared = to_stage_event(
        "rewrite_and_cost_gate",
        {
            "optimization": OptimizationResult(
                sql="SELECT 1",
                rules_applied=("push_down",),
                estimated_cost=4200.0,
                within_budget=True,
            )
        },
    )

    assert "narrow it by" not in facts(cleared)
    assert facts(cleared)["verdict"] == "within budget"
    assert facts(cleared)["estimated cost"] == "4200"


def test_timing_and_pass_number_travel_with_the_stage() -> None:
    """Neither is knowable from the delta: a node does not know when the one
    before it finished, and a node re-run after an escalated regeneration has
    no memory of the first pass."""
    event = to_stage_event("planning", {"plan": PLAN}, duration_ms=1_820, attempt=2)

    assert event.duration_ms == 1_820
    assert event.attempt == 2


def test_a_trail_stored_before_this_phase_still_reads_back() -> None:
    """Every field added here is defaulted, so a row written when a stage was
    only {stage, status, detail} validates as a stage that reported a line and
    nothing else — which is exactly what it was. The stored column is JSON, so
    widening the entity needs no migration; it does need this."""
    stored = {"stage": "planning", "status": "completed", "detail": "sum sales by month"}

    event = StageEvent.model_validate(stored)

    assert event.facts == ()
    assert event.duration_ms is None
    assert event.attempt == 1
