"""Builds candidate-generation strategies out of the CANDIDATE_STRATEGIES
registry.

Importing `genql.repositories.query` is what populates that registry: the
package imports each strategy module for its registration decorator. Nothing
here names a strategy class, so adding a strategy is one file plus one
decorator plus one import line in that package — never an edit here, and never
an edit in CandidateGenerationService.

`_DEFAULT_STRATEGY` is the one the non-contested path uses. The choice is
arbitrary — a non-contested plan has one intended reading, so strategy choice
cannot matter — but it is fixed rather than "whichever sorts first" so that
registering a third strategy cannot silently change the non-contested path.
"""

from __future__ import annotations

from collections.abc import Sequence

import genql.repositories.query  # noqa: F401 - registration side effect
from genql.domain.ports.candidate_strategy import CandidateGenerationStrategy
from genql.domain.ports.chat_provider import ChatProvider
from genql.repositories.query.registry import CANDIDATE_STRATEGIES

_DEFAULT_STRATEGY = "decomposition"


class CandidateStrategyFactoryImpl:
    def default(self, chat: ChatProvider) -> CandidateGenerationStrategy:
        return CANDIDATE_STRATEGIES.create(_DEFAULT_STRATEGY, chat=chat)

    def all(self, chat: ChatProvider) -> Sequence[CandidateGenerationStrategy]:
        return [
            CANDIDATE_STRATEGIES.create(key, chat=chat)
            for key in CANDIDATE_STRATEGIES.keys()  # noqa: SIM118 - Registry, not a dict
        ]
