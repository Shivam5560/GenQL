"""Three adapters for the three stages this phase inserts between static
validation and guarded execution. Their own file, matching how
query_turn_nodes.py was split out from query_nodes.py in Phase 6: one file per
responsibility, and this is the only module besides query_turn_nodes.py that
carries phase-specific business logic rather than a pass-through call.

Every node opens with the same guard from the spec's §7: not contested, or one
surviving candidate, short-circuits with no service call at all. This is what
makes the whole ambiguity machinery demand-driven at runtime, not only at the
registry level.
"""

from __future__ import annotations

from typing import Any

from genql.api.query_state import QueryState
from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.errors import CritiqueError, QueryError
from genql.domain.ports.critic import Critic
from genql.services.query.ambiguity_probing_service import AmbiguityProbingService
from genql.services.query.candidate_selection_service import CandidateSelectionService


class CritiqueNode:
    """Raises CritiqueError itself when exhausted (Deviation 1/2): granting
    the one escalated retry is a decision this node must make and act on
    using the `escalated` value it was handed, in the same evaluation that
    might flip it."""

    def __init__(self, service: Critic) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidates = state["candidates"]
        if not state["contested"] or len(candidates) <= 1:
            return {"critique_reports": ()}

        plan = state["plan"]
        if plan is None:
            raise CritiqueError("critique was reached without a plan")
        reports = self._service.critique(
            plan, candidates, state["validated_sqls"], state["links"] or ()
        )
        if reports and all(r.is_fatal for r in reports):
            if state["escalated"]:
                raise CritiqueError(
                    f"every surviving candidate for {state['question']!r} carries a "
                    "fatal defect, even after an escalated regeneration"
                )
            return {"critique_reports": reports, "escalated": True}
        return {"critique_reports": reports}


class AmbiguityProbingNode:
    def __init__(self, service: AmbiguityProbingService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidates = state["candidates"]
        if not state["contested"] or len(candidates) <= 1:
            return {"probe_results": ()}
        plan = state["plan"]
        if plan is None:
            raise QueryError("ambiguity probing was reached without a plan")
        results = self._service.probe(
            plan,
            candidates,
            state["validated_sqls"],
            state["critique_reports"],
            state["datasource_name"],
        )
        return {"probe_results": results}


class CandidateSelectionNode:
    def __init__(self, service: CandidateSelectionService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        candidates = state["candidates"]
        validated_sqls = state["validated_sqls"]
        if not state["contested"] or len(candidates) <= 1:
            selection = CandidateSelection(
                selected=candidates[0],
                selected_sql=validated_sqls[0],
                method="single_survivor",
                rationale="only one candidate survived validation",
            )
        else:
            selection = self._service.select(
                candidates, validated_sqls, state["critique_reports"], state["probe_results"]
            )
        return {"selection": selection, "validated_sql": selection.selected_sql}
