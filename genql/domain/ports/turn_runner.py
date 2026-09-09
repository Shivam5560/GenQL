"""One turn, start to finish, with no clarification loop.

What an evaluation run needs, and deliberately narrower than the CLI's path:
an evaluation cannot answer a clarifying question, so a paused turn is simply
a failed case. The implementation lives in `genql/api/` because it wraps the
compiled graph; the service depends on this protocol so that
`genql/services/` never imports `genql/api/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.turn_response import TurnResponse


@runtime_checkable
class TurnRunner(Protocol):
    def run(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> TurnResponse: ...
