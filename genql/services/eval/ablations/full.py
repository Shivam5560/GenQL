"""The baseline every other ablation's delta is measured against."""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.services.eval.registry import ABLATIONS


@ABLATIONS.register("full")
class FullAblation(Ablation):
    name: str = "full"
    description: str = "every enrichment layer enabled — the baseline"
