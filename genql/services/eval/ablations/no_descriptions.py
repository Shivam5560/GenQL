"""Descriptions, aliases, and units removed from the compiled search text.

The only ablation that needs a recompile: enrichment never reaches the online
path through a query-time read. SchemaLinkingService reads structural columns,
join paths, and metrics; descriptions influence a turn only through the BM25
text and the embedding that SearchDocumentCompiler assembles offline. A null
adapter at query time would switch off nothing and report a reassuring "no
delta" that meant only that the wrong thing had been disabled.
"""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.services.eval.registry import ABLATIONS


@ABLATIONS.register("no_descriptions")
class NoDescriptionsAblation(Ablation):
    name: str = "no_descriptions"
    description: str = "search documents compiled from structural fields only"
    setting_overrides: tuple[tuple[str, bool], ...] = (("enrichment_enabled", False),)
    requires_recompile: bool = True
