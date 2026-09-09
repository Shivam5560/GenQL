"""No probe queries; selection falls back to critique ranking."""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.services.eval.registry import ABLATIONS


@ABLATIONS.register("no_probing")
class NoProbingAblation(Ablation):
    name: str = "no_probing"
    description: str = "no probe queries; selection falls back to critique ranking"
    setting_overrides: tuple[tuple[str, bool], ...] = (("probing_enabled", False),)
