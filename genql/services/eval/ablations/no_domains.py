"""Domain scoping switched off: retrieval sees every object, unscoped."""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.services.eval.registry import ABLATIONS


@ABLATIONS.register("no_domains")
class NoDomainsAblation(Ablation):
    name: str = "no_domains"
    description: str = "domain scoping skipped; retrieval sees every object"
    setting_overrides: tuple[tuple[str, bool], ...] = (("domain_scoping_enabled", False),)
