"""Failures raised while running or extending the offline discovery pipeline."""

from __future__ import annotations

from genql.domain.errors.base import GenqlError


class DiscoveryError(GenqlError):
    """A discovery step could not complete."""


class CatalogAccessError(DiscoveryError):
    """The target warehouse catalog could not be read."""


class ProfilingError(DiscoveryError):
    """A column could not be profiled."""

    def __init__(self, qualified_name: str, reason: str) -> None:
        super().__init__(f"failed to profile {qualified_name}: {reason}")
        self.qualified_name = qualified_name


class UnknownDiscoveryStepError(DiscoveryError):
    """`--start-from` named a step that is not part of the pipeline."""

    def __init__(self, step_name: str, available: list[str]) -> None:
        options = ", ".join(available) or "<empty>"
        super().__init__(f"{step_name!r} is not a known discovery step. Available: {options}")
        self.step_name = step_name


class GraphProjectionError(DiscoveryError):
    """One schema's objects or FK edges could not be written into the graph."""


class GraphAnalysisError(DiscoveryError):
    """Clustering, embedding, or join-path mining could not complete."""


class EnrichmentError(DiscoveryError):
    """LLM object profiling or embedding could not complete."""


class DomainNamingError(DiscoveryError):
    """Fused clustering or LLM domain naming could not complete."""


class OverlayError(DiscoveryError):
    """semantic/<datasource>.yaml failed schema validation or named an unknown object."""


class CompileError(DiscoveryError):
    """genql_search_document could not be refreshed."""


class AmbiguityExampleGenerationError(DiscoveryError):
    """The offline synthetic ambiguity log could not be generated or embedded
    for one domain."""
