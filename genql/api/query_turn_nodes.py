"""Three adapters for the three stages prepended to Phase 5's graph.

They live in their own file rather than joining query_nodes.py for two
reasons: query_nodes.py is already the five generation-path adapters and one
file per responsibility is the house rule, and this is the only module in
genql/api/ that calls interrupt(), which is worth being able to find.

AmbiguityGateNode is the one that carries real behaviour, and it is written to
be idempotent under re-execution. LangGraph resumes an interrupted node by
running it AGAIN from its first line — interrupt() raises on the first pass and
returns the resume value on the second — so everything before the interrupt
call runs twice. Here that is one `assess` call whose result is overwritten,
which costs one model call and changes nothing. Anything with a side effect
would have to move after the interrupt.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from genql.api.query_state import QueryState
from genql.domain.ports.ambiguity_gate import AmbiguityGate
from genql.domain.ports.domain_scoper import DomainScoper
from genql.domain.ports.intent_classifier import IntentClassifier


class IntentClassificationNode:
    def __init__(self, classifier: IntentClassifier) -> None:
        self._classifier = classifier

    def __call__(self, state: QueryState) -> dict[str, Any]:
        return {"intent": self._classifier.classify(state["question"])}


def _answers(state: QueryState) -> tuple[tuple[str, str], ...]:
    """`clarifications` as tuples again, whatever the checkpointer gave back.

    A checkpoint round-trip serialises the tuple-of-pairs to JSON arrays and
    restores it as `[["entity", "stores"]]`, not `(("entity", "stores"),)`.
    Every resumed pass therefore sees lists, and without this the node would
    hand a list to a port typed `tuple[tuple[str, str], ...]` and then fail
    outright on `list + tuple` when appending the new answer. Normalising once,
    here, keeps that langgraph detail out of both the gate service and the
    router.
    """
    return tuple((dimension, answer) for dimension, answer in state["clarifications"])


class AmbiguityGateNode:
    def __init__(self, gate: AmbiguityGate) -> None:
        self._gate = gate

    def __call__(self, state: QueryState) -> dict[str, Any]:
        answers = _answers(state)
        assessment = self._gate.assess(state["question"], state["datasource_name"], answers)
        if not assessment.is_ambiguous:
            return {"ambiguity": assessment}
        # Both guards matter. Without a dimension there is nothing to record
        # the answer against, so the loop would not shrink and would not
        # terminate; without a question there is nothing to show the user, so
        # the turn would pause with no way to resume it. AmbiguityGateService
        # already refuses to produce either, and this refuses to act on one.
        dimension = assessment.missing_dimension
        question = assessment.clarifying_question
        if dimension is None or not question:
            return {"ambiguity": assessment}
        answer = interrupt(question)
        return {
            "ambiguity": assessment,
            "clarifications": answers + ((dimension, str(answer)),),
        }


class DomainScopingNode:
    def __init__(self, scoper: DomainScoper) -> None:
        self._scoper = scoper

    def __call__(self, state: QueryState) -> dict[str, Any]:
        # An explicit --domain-id wins: it is the documented manual override
        # for a question this heuristic would scope wrongly.
        if state["domain_id"] is not None:
            return {}
        return {"domain_id": self._scoper.resolve(state["question"], state["datasource_name"])}
