"""Mined join paths withheld from schema linking."""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.services.eval.registry import ABLATIONS


@ABLATIONS.register("no_join_paths")
class NoJoinPathsAblation(Ablation):
    name: str = "no_join_paths"
    description: str = "mined join paths withheld from schema linking"
    setting_overrides: tuple[tuple[str, bool], ...] = (("join_paths_enabled", False),)
