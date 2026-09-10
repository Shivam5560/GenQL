"""Stage 1 of the parent spec's §9: route away from SQL generation when SQL is
not the answer.

A deterministic pre-filter runs BEFORE the model call, the same way
AmbiguityGateService applies its YAML rules before scoring: a question whose
shape already settles the routing is not a judgment a model needs to make, and
skipping it removes a full sequential provider round trip from the common case
— every analytical turn, which is nearly all of them.

The pre-filter is deliberately asymmetric, and that asymmetry is what makes it
safe. It may only conclude `analytical_sql`; it can never route a question AWAY
from the pipeline. So its worst failure is that a question the model would have
short-circuited politely instead reaches the gate and gets asked a clarifying
question — a worse answer, not a wrong one. The dangerous direction, sending a
real analytical question to END, stays entirely with the model.

It also declines to fire on anything carrying conversational, schema-describing
or referential language, because those are exactly the three non-analytical
labels; when any such marker is present the model decides, as before.

The returned label is re-checked against QUESTION_INTENTS rather than trusted.
A structured-output call can still return a well-formed string that is not one
of the four, and letting that reach the graph's conditional edge would raise a
KeyError deep inside langgraph instead of a typed error here.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.errors import ChatProviderError, IntentClassificationError
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.value_objects.question_intent import QUESTION_INTENTS

_ANALYTICAL = "analytical_sql"

# Words that only appear when a question is asking for numbers or rows out of
# business data. A hit is necessary, not sufficient — every disqualifier below
# still has to miss.
_ANALYTICAL_MARKERS = frozenset(
    {
        "average",
        "avg",
        "count",
        "highest",
        "how many",
        "how much",
        "largest",
        "lowest",
        "max",
        "maximum",
        "mean",
        "median",
        "min",
        "minimum",
        "most",
        "least",
        "number of",
        "per",
        "rank",
        "revenue",
        "sales",
        "smallest",
        "sum",
        "top",
        "total",
        "bottom",
        "breakdown",
        "distribution",
        "trend",
    }
)

# Any of these and the model decides. `followup` markers ("instead", "also",
# "what about") matter as much as greetings: a refinement routes to a different
# branch than a fresh analytical question, and this filter cannot tell them
# apart.
_DISQUALIFIERS = frozenset(
    {
        # non_sql / conversational
        "hello",
        "hi ",
        "hey",
        "thanks",
        "thank you",
        "please explain",
        "who are you",
        "what can you",
        "help me understand",
        # metadata_question
        "what tables",
        "which tables",
        "what columns",
        "which columns",
        "what does",
        "what is the schema",
        "describe the",
        "list the tables",
        "schema",
        "column",
        "table",
        "mean by",
        "definition",
        # followup
        "instead",
        "what about",
        "also show",
        "same but",
        "previous",
        "that query",
        "earlier",
    }
)

_WORD_MARKERS = frozenset(m for m in _ANALYTICAL_MARKERS if " " not in m)
_PHRASE_MARKERS = frozenset(m for m in _ANALYTICAL_MARKERS if " " in m)


class IntentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: str


def classify_deterministically(question: str) -> str | None:
    """`analytical_sql` when the question's shape settles it, else None.

    None means "ask the model" — it is not a label and must never be treated
    as one.
    """
    text = f" {question.lower().strip()} "
    if any(d in text for d in _DISQUALIFIERS):
        return None
    if any(p in text for p in _PHRASE_MARKERS):
        return _ANALYTICAL
    words = set(re.findall(r"[a-z]+", text))
    if words & _WORD_MARKERS:
        return _ANALYTICAL
    return None


def build_intent_prompt(question: str) -> str:
    return (
        "Classify what a user is asking a data warehouse assistant.\n\n"
        f"Question:\n{question}\n\n"
        "Return `intent` as exactly one of these four labels:\n"
        "- analytical_sql: asks for numbers, aggregates, or rows that a SQL "
        "query over business data would answer.\n"
        "- metadata_question: asks about the schema itself — which tables or "
        "columns exist, what something means — not about the data in it.\n"
        "- followup: refines, corrects, or narrows a previous question, and "
        "cannot be answered without it.\n"
        "- non_sql: anything else, including greetings, instructions, and "
        "requests no database could answer.\n\n"
        "Return the label alone. Do not explain the choice."
    )


class IntentClassificationService:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def classify(self, question: str) -> str:
        settled = classify_deterministically(question)
        if settled is not None:
            return settled
        try:
            response = self._chat.complete(build_intent_prompt(question), IntentResponse)
        except (ChatProviderError, ValidationError) as exc:
            raise IntentClassificationError(f"failed to classify {question!r}: {exc}") from exc
        if response.intent not in QUESTION_INTENTS:
            raise IntentClassificationError(
                f"{response.intent!r} is not a known question intent. "
                f"Expected one of: {', '.join(QUESTION_INTENTS)}"
            )
        return response.intent
