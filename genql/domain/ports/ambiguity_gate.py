from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment


@runtime_checkable
class AmbiguityGate(Protocol):
    """Stage 2.

    Takes `datasource_name` rather than a pre-read tuple of rules so the
    implementation owns its RuleReader — reading genql_rule from the graph node
    would put repository access in the controller layer.

    Takes `answers` — the (dimension, answer) pairs already collected in this
    thread — because without them a resumed assessment cannot tell a resolved
    dimension from an unresolved one, and would re-ask the same question
    forever. With them, each round strictly shrinks a fixed six-element set.
    """

    def assess(
        self,
        question: str,
        datasource_name: str,
        answers: tuple[tuple[str, str], ...] = (),
    ) -> AmbiguityAssessment: ...
