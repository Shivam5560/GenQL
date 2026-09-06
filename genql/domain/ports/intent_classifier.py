from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IntentClassifier(Protocol):
    """Stage 1. Returns one of QUESTION_INTENTS; anything else is an error the
    implementation raises, not a value it returns."""

    def classify(self, question: str) -> str: ...
