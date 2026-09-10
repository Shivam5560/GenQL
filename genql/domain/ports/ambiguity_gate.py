from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.schema_link import SchemaLink


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

    Takes `links` — schema_linking's output, now computed before the gate runs
    — so an implementation can drop a dimension the schema cannot express (no
    date column in scope, say) instead of relying on the model to notice.
    Defaults to `()` so a caller with no schema knowledge yet (or a fake in a
    test) need not pass anything and gets the pre-schema-aware behaviour.

    Takes `known_scores` — every per-dimension confidence a previous call
    already measured for this exact question — so a resumed assessment does
    not pay a model call to re-confirm a dimension nothing has changed about.
    The returned `AmbiguityAssessment.dimension_scores` is the caller's cache
    to persist and pass back on the next round.
    """

    def assess(
        self,
        question: str,
        datasource_name: str,
        answers: tuple[tuple[str, str], ...] = (),
        links: tuple[SchemaLink, ...] = (),
        known_scores: tuple[tuple[str, float], ...] = (),
    ) -> AmbiguityAssessment: ...
