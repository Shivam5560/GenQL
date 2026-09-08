"""One offline, synthetic ambiguity example: a question, the interpretations
it admits, and which one is correct and why.

Written once per domain by SyntheticAmbiguityLogService, read by similarity to
the current question as few-shot context for the contested generation path —
a different key and a different consumer than genql_search_document's
schema-object retrieval, which is why this is its own table rather than an
extension of that one.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AmbiguityExample(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    interpretations: tuple[str, ...]
    resolution: str
    domain_id: int | None = None
