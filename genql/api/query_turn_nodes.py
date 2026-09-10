"""Four adapters for the stages prepended to Phase 5's graph.

They live in their own file rather than joining query_nodes.py for two
reasons: query_nodes.py is already the five generation-path adapters and one
file per responsibility is the house rule, and this is the only module in
genql/api/ that calls interrupt(), which is worth being able to find.

AmbiguityGateNode (the model call) and AmbiguityInterruptNode (the pause) are
split into two nodes rather than one, specifically so the expensive part is
never in front of an interrupt() call. LangGraph resumes an interrupted node
by running it AGAIN from its first line — interrupt() raises on the first pass
and returns the resume value on the second — so everything before the
interrupt call runs twice. When the assess() call sat before interrupt() in
one node, that meant a full, real model call was thrown away on every single
clarification round, guaranteed, every time — confirmed costing 4-9s live.
Moving the interrupt into its own node means the only thing that reruns on
resume is a state read, not a provider call: AmbiguityGateNode always returns
normally (never interrupts, so its result is always committed to state
before the pause), and AmbiguityInterruptNode's only job is to read the
already-committed assessment and pause if it says to.

The two-node cycle (gate -> interrupt -> gate -> ...) still terminates by the
same proof the single-node self-loop always had: each full cycle resolves one
more dimension from a fixed six-element set.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from genql.api.query_state import QueryState
from genql.domain.errors import AmbiguityGateError
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


def _known_scores(state: QueryState) -> tuple[tuple[str, float], ...]:
    """`gate_scores` as tuples again — the same checkpoint round-trip
    normalisation `_answers` does, for the same reason."""
    return tuple((dimension, confidence) for dimension, confidence in state["gate_scores"])


class AmbiguityGateNode:
    """Never interrupts — only assesses and returns. Always a normal return,
    so its result (the assessment, and the gate_scores cache) is always
    committed to state before any pause can happen, in AmbiguityInterruptNode."""

    def __init__(self, gate: AmbiguityGate, contested_min_resolved: int = 1) -> None:
        self._gate = gate
        self._contested_min_resolved = contested_min_resolved

    def __call__(self, state: QueryState) -> dict[str, Any]:
        answers = _answers(state)
        assessment = self._gate.assess(
            state["question"],
            state["datasource_name"],
            answers,
            state["links"] or (),
            _known_scores(state),
        )
        if not assessment.is_ambiguous:
            # Contested per Phase 6.5's original definition: any resumed
            # answer or applied rule default at all. That definition treats
            # "the gate needed to interrupt once" as proof the whole question
            # is ambiguous enough to warrant multi-candidate generation,
            # critique, and probing — but live testing showed almost every
            # analytical question against a sales-shaped schema gets asked
            # about time_range at least once, so this made "contested" (and
            # its full expensive path) the common case rather than the
            # exception the spec intended it to be.
            #
            # `contested_min_resolved` raises the bar: contested now requires
            # at least this many DISTINCT dimensions to have needed an answer
            # FROM THE USER (one entry per dimension in `answers` by
            # construction, so counting entries already counts distinct
            # dimensions). One narrow gap, cleanly closed by one clarifying
            # answer, is not the same signal as a question that was unclear
            # along several axes at once — the latter is what actually
            # predicts that a single generated candidate might guess wrong on
            # some OTHER dimension the gate never explicitly asked about,
            # which is what critique and probing exist to catch. Defaults to 1
            # (every prior behaviour, unchanged) so no caller that does not
            # pass this is affected; production wires a higher value via
            # Settings.
            #
            # `applied_defaults` is deliberately NOT counted, though it was
            # until this comment was written. A rule default is a dimension
            # somebody already answered once, in YAML, for every question
            # against this datasource — the opposite of evidence that THIS
            # question is unclear. Counting it made contested unavoidable
            # rather than exceptional: `semantic/local.yaml` alone defaults
            # time_range and comparison_baseline, so at a threshold of 2
            # every turn against `local` was contested before the user typed
            # anything, which is precisely the "contested is the common case"
            # problem the threshold was raised to fix.
            contested = len(answers) >= self._contested_min_resolved
            return {
                "ambiguity": assessment,
                "contested": contested,
                "gate_scores": assessment.dimension_scores,
                "assumptions": assessment.assumed,
            }
        return {
            "ambiguity": assessment,
            "gate_scores": assessment.dimension_scores,
            "assumptions": assessment.assumed,
        }


class AmbiguityInterruptNode:
    """The only interrupt() call in the graph, and nothing else. Reads an
    assessment AmbiguityGateNode already committed to state — never computes
    one — so re-execution on resume costs a dict read, not a model call."""

    def __call__(self, state: QueryState) -> dict[str, Any]:
        assessment = state["ambiguity"]
        if assessment is None or not assessment.is_ambiguous:
            return {}
        # Both guards matter. Without a dimension there is nothing to record
        # the answer against, so the loop would not shrink and would not
        # terminate; without a question there is nothing to show the user, so
        # the turn would pause with no way to resume it. AmbiguityGateService
        # already refuses to produce either; this is defence in depth against
        # a future implementation of the port that doesn't.
        dimension = assessment.missing_dimension
        question = assessment.clarifying_question
        if dimension is None or not question:
            raise AmbiguityGateError(
                "the gate reported ambiguous with no dimension or no question to ask"
            )
        # A mapping, not the bare question string. The pause is the only
        # channel from the gate to whoever is answering, so a suggestion that
        # does not travel in this payload cannot be offered as a one-tap
        # answer — the client would have nothing but prose to render. The
        # resume value is unaffected: it is still the answer text.
        answer = interrupt(
            {
                "question": question,
                "suggested_answer": assessment.suggested_answer,
                "options": assessment.options,
            }
        )
        return {"clarifications": _answers(state) + ((dimension, str(answer)),)}


class DomainScopingNode:
    def __init__(self, scoper: DomainScoper) -> None:
        self._scoper = scoper

    def __call__(self, state: QueryState) -> dict[str, Any]:
        # An explicit --domain-id wins: it is the documented manual override
        # for a question this heuristic would scope wrongly.
        if state["domain_id"] is not None:
            return {}
        return {"domain_id": self._scoper.resolve(state["question"], state["datasource_name"])}
