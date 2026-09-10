"""One reading per pipeline node, keyed by node name.

A node with no entry here still produces an event — the same open/closed
property the lookup has always had, so a stage added by a later phase streams
without anyone editing this file. What changed is that the four nodes which
previously had no entry (intent classification, domain scoping, critique, the
interrupt's own node) now have one: a stage that reports nothing is
indistinguishable from a stage that did not run, and that ambiguity is what
made a reading client sort stages which had genuinely run to the bottom of its
list.

Every reading is built from the node's delta alone. Nothing here reaches into
`QueryState`, calls a service, or re-derives a decision — a summariser that
could disagree with the stage it summarises is worse than no summariser.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from genql.api.sse.stage_summary import StageSummary, joined, reported, skipped


def _yes_no(value: object) -> str:
    return "yes" if value else "no"


def _intent(delta: dict[str, Any]) -> StageSummary:
    intent = delta.get("intent")
    if not intent:
        return skipped("the classifier named no intent for this question")
    return reported(f"read as {intent}", ("intent", str(intent)))


def _domain_scoping(delta: dict[str, Any]) -> StageSummary:
    # DomainScopingNode returns an empty delta when --domain-id was supplied:
    # the documented manual override, not a stage that failed to decide.
    if "domain_id" not in delta:
        return skipped("a domain was supplied with the question")
    domain_id = delta["domain_id"]
    if domain_id is None:
        return skipped("no business domain matched — the whole catalogue stays in scope")
    return reported(f"scoped to domain {domain_id}", ("domain_id", str(domain_id)))


def _schema_linking(delta: dict[str, Any]) -> StageSummary:
    links = delta.get("links") or ()
    columns = sum(len(link.column_names) for link in links)
    joins = sum(len(link.join_paths) for link in links)
    metrics = sum(len(link.metric_names) for link in links)
    return reported(
        f"{len(links)} objects linked",
        ("objects", str(len(links))),
        ("columns", str(columns)),
        ("join paths", str(joins)),
        ("metrics", str(metrics)),
        ("linked", ", ".join(link.object_qualified_name for link in links)),
    )


def _ambiguity_gate(delta: dict[str, Any]) -> StageSummary:
    """The richest delta in the pipeline, and the one that used to reach the
    browser as a Python dict repr — six lines of quoted keys that a reading
    client detected and threw away wholesale."""
    assessment = delta.get("ambiguity")
    if assessment is None:
        return skipped("the gate produced no assessment")
    scores = joined(tuple(assessment.dimension_scores))
    assumed = " · ".join(f"{dimension}={value}" for dimension, value in assessment.assumed)
    defaults = " · ".join(
        f"{dimension} via {rule}" for dimension, rule in assessment.applied_defaults
    )
    if assessment.is_ambiguous:
        return reported(
            f"asking about {assessment.missing_dimension}",
            ("asking about", str(assessment.missing_dimension or "")),
            ("confidence", scores),
            ("assumed", assumed),
            ("rule defaults", defaults),
        )
    return reported(
        f"{len(assessment.assumed)} dimensions assumed, none left to ask",
        ("confidence", scores),
        ("assumed", assumed),
        ("rule defaults", defaults),
        ("contested", _yes_no(delta.get("contested"))),
    )


def _ambiguity_interrupt(delta: dict[str, Any]) -> StageSummary:
    """The resumed pass. The interrupting pass never reaches here — it arrives
    as the `__interrupt__` pseudo-node, handled by the dispatcher."""
    clarifications = delta.get("clarifications") or ()
    if not clarifications:
        return skipped("the gate had nothing left to ask")
    dimension, answer = clarifications[-1]
    return reported(
        f"you answered {dimension}",
        ("dimension", str(dimension)),
        ("your answer", str(answer)),
        ("rounds", str(len(clarifications))),
    )


def _planning(delta: dict[str, Any]) -> StageSummary:
    plan = delta.get("plan")
    if plan is None:
        return skipped("no plan was produced")
    return reported(
        plan.plan_text,
        ("plan", plan.plan_text),
        ("grounded in", ", ".join(plan.referenced_objects)),
    )


def _candidates(delta: dict[str, Any]) -> StageSummary:
    candidates = delta.get("candidates") or ()
    return reported(
        f"{len(candidates)} candidates generated",
        ("candidates", str(len(candidates))),
        ("regenerations", str(delta.get("retry_count") or 0)),
    )


def _rules(violations: tuple[Any, ...]) -> str:
    return " · ".join(f"{v.rule_name}: {v.message}" for v in violations)


def _static_validation(delta: dict[str, Any]) -> StageSummary:
    cleared = delta.get("validated_sqls") or ()
    violations = tuple(delta.get("violations") or ())
    if cleared:
        return reported(
            f"{len(cleared)} candidates cleared validation",
            ("cleared", str(len(cleared))),
            ("guardrails fired", _rules(violations)),
        )
    return reported(
        "no candidate cleared — regenerating with the violations as feedback",
        ("cleared", "0"),
        ("guardrails fired", _rules(violations)),
        ("repairable", _yes_no(any(v.repairable for v in violations))),
        ("escalated", "yes" if delta.get("escalated") else ""),
    )


def _critique(delta: dict[str, Any]) -> StageSummary:
    reports = delta.get("critique_reports") or ()
    if not reports:
        return skipped("not contested, or only one candidate survived validation")
    scores = tuple((f"#{r.candidate_index}", f"{r.score:.2f}") for r in reports)
    defects = " · ".join(
        f"#{r.candidate_index} {d.severity}: {d.message}" for r in reports for d in r.defects
    )
    return reported(
        f"{len(reports)} candidates scored",
        ("scores", joined(scores)),
        ("defects", defects),
        ("fatal", str(sum(1 for r in reports if r.is_fatal))),
    )


def _probes(delta: dict[str, Any]) -> StageSummary:
    results = delta.get("probe_results") or ()
    if not results:
        return skipped("not contested, or critique had already decided")
    resolved = tuple(
        f"#{r.resolved_candidate_index}" for r in results if r.resolved_candidate_index is not None
    )
    return reported(
        f"{len(results)} probes executed",
        ("probes", str(len(results))),
        ("dimensions", ", ".join(r.probe.dimension for r in results)),
        ("warehouse said", " · ".join(r.actual_result for r in results)),
        ("resolved to", ", ".join(resolved)),
    )


def _selection(delta: dict[str, Any]) -> StageSummary:
    selection = delta.get("selection")
    if selection is None:
        return skipped("no candidate was selected")
    return reported(
        f"selected by {selection.method}",
        ("method", selection.method),
        ("why", selection.rationale),
    )


def _optimization(delta: dict[str, Any]) -> StageSummary:
    optimization = delta.get("optimization")
    if optimization is None:
        return skipped("the cost gate produced no verdict")
    rules = ", ".join(optimization.rules_applied) or "no rewrites"
    verdict = "within budget" if optimization.within_budget else "over budget"
    return reported(
        f"{rules}; estimated cost {optimization.estimated_cost:.0f} ({verdict})",
        ("rewrites", rules),
        ("estimated cost", f"{optimization.estimated_cost:.0f}"),
        ("verdict", verdict),
        ("narrow it by", optimization.narrowing_suggestion or ""),
    )


def _execution(delta: dict[str, Any]) -> StageSummary:
    result = delta.get("result")
    if result is None:
        return skipped("the statement was not run")
    return reported(
        f"{result.row_count} rows",
        ("rows", str(result.row_count)),
        ("columns", str(len(result.columns))),
        ("truncated", _yes_no(result.truncated)),
    )


SUMMARISERS: dict[str, Callable[[dict[str, Any]], StageSummary]] = {
    "intent_classification": _intent,
    "domain_scoping": _domain_scoping,
    "schema_linking": _schema_linking,
    "ambiguity_gate": _ambiguity_gate,
    "ambiguity_interrupt": _ambiguity_interrupt,
    "planning": _planning,
    "candidate_generation": _candidates,
    "static_validation": _static_validation,
    "critique": _critique,
    "ambiguity_probing": _probes,
    "candidate_selection": _selection,
    "rewrite_and_cost_gate": _optimization,
    "guarded_execution": _execution,
}
