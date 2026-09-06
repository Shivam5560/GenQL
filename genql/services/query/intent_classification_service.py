"""Stage 1 of the parent spec's §9: route away from SQL generation when SQL is
not the answer.

One ChatProvider.complete call, using the same grounded-call pattern
PlanningService established — a validated Pydantic response, not prose to
parse. The model is asked for a bare label rather than a label plus a
rationale: nothing downstream reads a rationale, and asking for one would pay
output tokens (five times input, per the parent spec's §20) for text nobody
sees.

The returned label is re-checked against QUESTION_INTENTS rather than trusted.
A structured-output call can still return a well-formed string that is not one
of the four, and letting that reach the graph's conditional edge would raise a
KeyError deep inside langgraph instead of a typed error here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.errors import ChatProviderError, IntentClassificationError
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.value_objects.question_intent import QUESTION_INTENTS


class IntentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: str


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
