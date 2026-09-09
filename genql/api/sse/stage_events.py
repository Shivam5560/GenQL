"""One completed node becomes one short line.

The summarisers are a lookup keyed by node name, and a node with no entry
still produces an event — so a stage added by a later phase streams without
anyone editing this file, which is the same open/closed property the
registries give the rest of the system.

Every detail is capped. A plan can be a thousand tokens and a candidate set can
be several statements; the stream exists to say *what is happening*, and the
full state is available from the terminal event.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from genql.domain.entities.stage_event import StageEvent

_MAX_DETAIL = 200
_INTERRUPT = "__interrupt__"


def _links(delta: dict[str, Any]) -> str:
    return f"{len(delta.get('links') or ())} objects linked"


def _plan(delta: dict[str, Any]) -> str:
    plan = delta.get("plan")
    return plan.plan_text if plan is not None else "planned"


def _candidates(delta: dict[str, Any]) -> str:
    return f"{len(delta.get('candidates') or ())} candidates generated"


def _validated(delta: dict[str, Any]) -> str:
    return f"{len(delta.get('validated_sqls') or ())} candidates cleared validation"


def _probes(delta: dict[str, Any]) -> str:
    return f"{len(delta.get('probe_results') or ())} probes executed"


def _selection(delta: dict[str, Any]) -> str:
    selection = delta.get("selection")
    return f"selected by {selection.method}" if selection is not None else "selected"


def _optimization(delta: dict[str, Any]) -> str:
    optimization = delta.get("optimization")
    if optimization is None:
        return "cost gate cleared"
    rules = ", ".join(optimization.rules_applied) or "no rewrites"
    verdict = "within budget" if optimization.within_budget else "over budget"
    return f"{rules}; estimated cost {optimization.estimated_cost:.0f} ({verdict})"


def _execution(delta: dict[str, Any]) -> str:
    result = delta.get("result")
    return f"{result.row_count} rows" if result is not None else "executed"


_SUMMARISERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "schema_linking": _links,
    "planning": _plan,
    "candidate_generation": _candidates,
    "static_validation": _validated,
    "ambiguity_probing": _probes,
    "candidate_selection": _selection,
    "rewrite_and_cost_gate": _optimization,
    "guarded_execution": _execution,
}


def to_stage_event(node: str, delta: Any) -> StageEvent:
    if node == _INTERRUPT:
        question = str(delta[0].value) if delta else ""
        return StageEvent(stage="ambiguity_gate", status="paused", detail=question[:_MAX_DETAIL])

    summarise = _SUMMARISERS.get(node)
    detail = summarise(delta) if summarise and isinstance(delta, dict) else None
    return StageEvent(
        stage=node, status="completed", detail=detail[:_MAX_DETAIL] if detail else None
    )
