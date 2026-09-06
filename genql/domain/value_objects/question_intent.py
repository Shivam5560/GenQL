"""The four intents stage 1 routes on.

A plain tuple constant rather than a Registry: nothing registers a per-intent
*implementation*. Only `analytical_sql` proceeds past intent classification,
and the other three all map to the same "explain what this cannot do yet"
response, so there is no second implementation for a registry to hold.
"""

from __future__ import annotations

QUESTION_INTENTS: tuple[str, ...] = (
    "analytical_sql",
    "metadata_question",
    "followup",
    "non_sql",
)
