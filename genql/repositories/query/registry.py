"""The candidate-generation strategy registry, keyed by strategy name.

Mirrors GUARDRAILS exactly: one file plus one decorator adds a strategy.
CandidateGenerationService iterates CANDIDATE_STRATEGIES.keys() only on the
contested path — the non-contested path always names "decomposition"
directly, so a third registered strategy changes contested-path diversity
without touching CandidateGenerationService at all.
"""

from __future__ import annotations

from genql.domain.ports.candidate_strategy import CandidateGenerationStrategy
from genql.registries.registry import Registry

CANDIDATE_STRATEGIES: Registry[CandidateGenerationStrategy] = Registry("candidate_strategies")
