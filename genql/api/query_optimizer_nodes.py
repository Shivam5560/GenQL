"""The adapter between QueryState and OptimizationService.

Its own module rather than another class in query_nodes.py, following the
convention query_turn_nodes.py and query_ambiguity_nodes.py established: a
phase's new nodes get a file named for the phase, so a reader can find them.

The node writes `validated_sql` even when the gate refuses to run the query.
That looks odd until you read the CLI: a user told "this was too expensive"
wants to see the statement that was too expensive, and the router — not the
presence of SQL — is what decides whether execution happens.
"""

from __future__ import annotations

from typing import Any

from genql.api.query_state import QueryState
from genql.domain.errors import OptimizationError
from genql.services.query.optimization_service import OptimizationService


class RewriteAndCostGateNode:
    def __init__(self, service: OptimizationService) -> None:
        self._service = service

    def __call__(self, state: QueryState) -> dict[str, Any]:
        selection = state["selection"]
        if selection is None:
            raise OptimizationError("the cost gate was reached without a selected candidate")
        plan = state["plan"]
        if plan is None:
            raise OptimizationError("the cost gate was reached without a plan")

        result = self._service.optimize(
            plan, selection.selected_sql, state["links"] or (), state["datasource_name"]
        )
        return {"optimization": result, "validated_sql": result.sql}
