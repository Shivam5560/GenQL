"""One completed node becomes one event.

The reading of each node's delta lives in `stage_summaries`; this file is the
dispatch around it — which node, which status, and the two things a summariser
cannot know because they are properties of the stream rather than of the
delta: how long the stage took, and how many times it has run this turn.

The interrupt is handled here rather than in the lookup because it is not a
node. LangGraph reports a pause as the `__interrupt__` pseudo-key, and its
payload is the mapping `AmbiguityInterruptNode` passed to `interrupt()` — so
the question is read out of that mapping by key. It used to be stringified
whole, which put a Python dict repr on the wire (`{'question': '…',
'suggested_answer': '…', 'options': (…)}`) and left the browser to detect the
blob and drop it. The suggestion and the options travel as facts instead,
where a client can render them without parsing anything.
"""

from __future__ import annotations

from typing import Any

from genql.api.sse.stage_summaries import SUMMARISERS
from genql.api.sse.stage_summary import MAX_DETAIL, StageSummary, reported, trim
from genql.domain.entities.stage_event import StageEvent

_INTERRUPT = "__interrupt__"
# The pause belongs to the gate, not to the node that raised it: a reader
# looking for "why was I asked this" looks at the gate.
_INTERRUPT_STAGE = "ambiguity_gate"


def _interrupt_summary(delta: Any) -> StageSummary:
    """The gate's question, plus what it would have accepted for an answer."""
    payload = delta[0].value if delta else None
    if not isinstance(payload, dict):
        # A port that passes the bare question string rather than the mapping.
        # Still perfectly usable; there is simply nothing to offer beside it.
        return reported(trim(str(payload or ""), MAX_DETAIL))
    options = payload.get("options") or ()
    return reported(
        str(payload.get("question") or ""),
        ("question", str(payload.get("question") or "")),
        ("suggested answer", str(payload.get("suggested_answer") or "")),
        ("options", ", ".join(str(option) for option in options)),
    )


def to_stage_event(
    node: str,
    delta: Any,
    duration_ms: int | None = None,
    attempt: int = 1,
) -> StageEvent:
    if node == _INTERRUPT:
        summary = _interrupt_summary(delta)
        return StageEvent(
            stage=_INTERRUPT_STAGE,
            status="paused",
            detail=summary.detail,
            facts=summary.facts,
            duration_ms=duration_ms,
            attempt=attempt,
        )

    summarise = SUMMARISERS.get(node)
    summary = (
        summarise(delta)
        if summarise is not None and isinstance(delta, dict)
        else StageSummary(detail=None)
    )
    return StageEvent(
        stage=node,
        status="completed" if summary.did_run else "skipped",
        detail=summary.detail,
        facts=summary.facts,
        duration_ms=duration_ms,
        attempt=attempt,
    )
