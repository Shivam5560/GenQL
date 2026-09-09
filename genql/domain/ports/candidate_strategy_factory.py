"""Builds the CandidateGenerationStrategy instances one generation call needs.

CandidateGenerationService must not know that strategies live in a registry
under `genql.repositories`, any more than StaticValidationService knows that
guardrails do: the service states which strategies it wants — the one fixed
strategy for the non-contested path, or every registered strategy for the
contested one — and this port decides what that means. Mirrors
`GuardrailFactory` exactly, so the layering rule "services never import
repositories" holds without an import-linter exemption.

`chat` is a parameter rather than a constructor dependency because the
escalated regeneration swaps in a different ChatProvider for the same set of
strategies, and a factory bound to one provider could not express that.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.ports.candidate_strategy import CandidateGenerationStrategy
from genql.domain.ports.chat_provider import ChatProvider


@runtime_checkable
class CandidateStrategyFactory(Protocol):
    def default(self, chat: ChatProvider) -> CandidateGenerationStrategy:
        """The single strategy the non-contested path uses."""
        ...

    def all(self, chat: ChatProvider) -> Sequence[CandidateGenerationStrategy]:
        """Every registered strategy, in a stable order."""
        ...
