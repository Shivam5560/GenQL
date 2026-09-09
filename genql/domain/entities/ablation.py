"""A named set of settings overrides that switches one enrichment layer off.

It carries no behaviour on purpose. An ablation that could *do* something
would be a place for a service to branch on being ablated, and a service that
branches on being ablated is not the service being measured.

`requires_recompile` is true only for no_descriptions, because descriptions
reach the online path through compiled search documents rather than through a
query-time read — so switching them off means rebuilding those documents, not
swapping an adapter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Ablation(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    setting_overrides: tuple[tuple[str, bool], ...] = ()
    requires_recompile: bool = False
