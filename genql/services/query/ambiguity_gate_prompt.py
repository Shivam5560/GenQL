"""What the ambiguity gate asks the model, and the shape it expects back.

Split out of ambiguity_gate_service.py to stay under the house file-length
limit, along the seam the file already had: this module is the provider
contract (one prompt, one response schema), and the service beside it is the
policy that decides what to do with the answer. Nothing here reads state or
makes a decision, which is why it tests as a pure function.

Every field but `scores`, `clarifying_dimension`, and `clarifying_question`
carries a default. That is deliberate rather than lax: `assumption`,
`suggested_answer`, and `options` improve a question when present and cost
nothing when absent, so a provider that omits them should degrade the turn
to "no chips, no assumptions" rather than fail it outright.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DimensionScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    confidence: float
    # What the gate would apply for this dimension if it never got to ask.
    # Read only for dimensions the question budget suppressed.
    assumption: str = ""


class GateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    scores: tuple[DimensionScore, ...]
    # Which dimension `clarifying_question` actually asks about. Returned
    # rather than re-derived, because the two must agree: the caller records
    # the user's answer against this dimension and removes it from the open
    # set, so a question about `filter` filed under `time_range` both answers
    # the wrong dimension and permanently closes one that was never asked.
    clarifying_dimension: str
    clarifying_question: str
    # The answer the gate expects, and a couple of plausible alternatives, so
    # the UI can offer them as one-tap choices. The chips are an affordance,
    # and a question without them is still a question worth asking.
    suggested_answer: str = ""
    options: tuple[str, ...] = ()


def build_gate_prompt(
    question: str,
    open_dimensions: tuple[str, ...],
    answers: tuple[tuple[str, str], ...],
) -> str:
    context = "\n".join(f"- {dimension}: {answer}" for dimension, answer in answers) or (
        "- (none yet)"
    )
    dimensions = "\n".join(f"- {dimension}" for dimension in open_dimensions)
    return (
        "You are judging how completely an analytical question specifies what "
        "it wants, so a SQL generator does not have to guess.\n\n"
        f"Question:\n{question}\n\n"
        f"Already clarified by the user:\n{context}\n\n"
        f"Dimensions still to judge:\n{dimensions}\n\n"
        "Rules:\n"
        "- For each dimension listed above, return a `confidence` between 0.0 "
        "and 1.0 that the question (plus the clarifications) already specifies "
        "it well enough to write SQL without guessing.\n"
        "- Judge only the dimensions listed. Do not invent others.\n"
        "- For each dimension, also return an `assumption`: the single most "
        "reasonable reading a competent analyst would apply if nobody could "
        "be asked. State it as the decision itself, not as a question — "
        '"the last 12 months", "all sales channels", "no comparison". This '
        "is applied verbatim when there is no budget left to ask, so a "
        "dimension the question already specifies needs no assumption.\n"
        "- Return `clarifying_dimension`: the LOWEST-confidence dimension, "
        "copied exactly from the list above.\n"
        "- Return `clarifying_question`: a single, specific question about "
        "`clarifying_dimension` and nothing else. Ask about one thing. Never "
        "ask a compound question and never present a form.\n"
        "- Return `suggested_answer`: the answer you would apply for "
        "`clarifying_dimension` if the user simply pressed enter — normally "
        "the same as that dimension's `assumption`.\n"
        "- Return `options`: up to three short, concrete alternatives for "
        "`clarifying_dimension`, phrased as answers a person could pick "
        "rather than as questions. Omit them when the dimension has no small "
        "set of plausible answers."
    )
