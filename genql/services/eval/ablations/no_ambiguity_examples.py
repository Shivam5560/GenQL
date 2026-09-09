"""No synthetic few-shot examples during generation."""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.services.eval.registry import ABLATIONS


@ABLATIONS.register("no_ambiguity_examples")
class NoAmbiguityExamplesAblation(Ablation):
    name: str = "no_ambiguity_examples"
    description: str = "no synthetic few-shot examples during generation"
    setting_overrides: tuple[tuple[str, bool], ...] = (("ambiguity_examples_enabled", False),)
