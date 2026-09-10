"""One pipeline stage's outcome, as an SSE client and a stored trail see it.

Three fields carry the explanation, and they are deliberately different kinds
of thing:

`detail` is one short human line — never the state delta. A stage's delta can
contain the whole schema-link set or every candidate statement, and shipping
that down an event stream would make the transport the widest interface in the
system.

`facts` is the same stage's decision as label/value pairs, so a reader can
render "3 of 4 cleared, 1 repaired" as three values rather than parse it out of
a sentence. Pairs rather than a mapping, matching `applied_defaults` and
`assumed` elsewhere in this package: a frozen model needs hashable fields, and
a tuple of pairs round-trips through the JSON column unchanged. Both the pair
count and each value are capped by the summariser that builds them — the point
is to explain a decision, not to mirror the state.

`status` has a fourth member the first three phases did without. A pipeline
this demand-driven skips stages as a matter of course — critique and probing
short-circuit whenever a turn is uncontested — and `completed` with nothing to
say is indistinguishable from a stage that ran and found nothing. That
ambiguity is what made a reading client sort three stages that had genuinely
run to the bottom of its list, greyed out, behind stages that ran after them.
A stage that did not run says so.

`duration_ms` is measured by the caller draining the graph, not by the node:
the node does not know when the previous one finished, and the stream does.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

StageStatus = Literal["completed", "paused", "failed", "skipped"]


class StageEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: str
    status: StageStatus
    detail: str | None = None
    # Defaulted, every one of them: a row written before this phase reads back
    # as a stage that reported a line and nothing else, which is exactly what
    # it was. Widening the entity must not invalidate stored history.
    facts: tuple[tuple[str, str], ...] = ()
    duration_ms: int | None = None
    # Which pass this was. Static validation and candidate generation can run
    # twice for one turn — once, then again on the escalated regeneration — and
    # a trail that lists the stage twice without saying so reads as a bug.
    attempt: int = 1
