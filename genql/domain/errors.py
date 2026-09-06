"""Typed failures. Every stage returns one of these so callers can route."""

from __future__ import annotations


class GenqlError(Exception):
    """Base class for every GenQL failure."""


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


class DatasourceError(GenqlError):
    """A datasource or schema registration could not be resolved."""


class UnknownDatasourceError(DatasourceError):
    def __init__(self, name: str, available: list[str]) -> None:
        options = ", ".join(available) or "<none registered>"
        super().__init__(f"{name!r} is not a registered datasource. Available: {options}")
        self.name = name


class DuplicateDatasourceError(DatasourceError):
    def __init__(self, name: str) -> None:
        super().__init__(f"datasource {name!r} is already registered")
        self.name = name


class MissingDatasourceSecretError(DatasourceError):
    """The environment variable a datasource names is unset or empty."""

    def __init__(self, datasource_name: str, env_var: str) -> None:
        super().__init__(
            f"datasource {datasource_name!r} names environment variable {env_var!r}, "
            "which is unset or empty"
        )
        self.datasource_name = datasource_name
        self.env_var = env_var


class EmptySchemaError(DatasourceError):
    """Registration found no readable objects in the named schema.

    Distinct from UnknownSchemaRegistrationError, which means "no such row in
    the semantic store". A reader that returns nothing cannot tell an empty
    schema apart from an absent one or one this role cannot see, so the
    message names all three rather than asserting the wrong one.
    """

    def __init__(self, qualified_name: str) -> None:
        super().__init__(
            f"{qualified_name!r} exposes no readable objects: it is empty, does not "
            "exist, or is not visible to the role this datasource connects as"
        )
        self.qualified_name = qualified_name


class UnknownSchemaRegistrationError(DatasourceError):
    def __init__(self, qualified_name: str, available: list[str]) -> None:
        options = ", ".join(available) or "<none registered>"
        super().__init__(f"{qualified_name!r} is not a registered schema. Available: {options}")
        self.qualified_name = qualified_name


class AmbiguousScopeError(DatasourceError):
    """No datasource was given and more than one is enabled."""

    def __init__(self, candidates: list[str]) -> None:
        options = ", ".join(candidates)
        super().__init__(
            f"no datasource given and {len(candidates)} are enabled ({options}). "
            "Pass --datasource, or set GENQL_DEFAULT_DATASOURCE."
        )
        self.candidates = candidates


class GraphProjectionError(DiscoveryError):
    """One schema's objects or FK edges could not be written into the graph."""


class GraphAnalysisError(DiscoveryError):
    """Clustering, embedding, or join-path mining could not complete."""


class ChatProviderError(GenqlError):
    """A ChatProvider implementation could not complete a call."""


class EmbeddingProviderError(GenqlError):
    """An EmbeddingProvider implementation could not complete a call."""


class RerankProviderError(GenqlError):
    """A RerankProvider implementation could not complete a call."""


class EnrichmentError(DiscoveryError):
    """LLM object profiling or embedding could not complete."""


class DomainNamingError(DiscoveryError):
    """Fused clustering or LLM domain naming could not complete."""


class OverlayError(DiscoveryError):
    """semantic/<datasource>.yaml failed schema validation or named an unknown object."""


class CompileError(DiscoveryError):
    """genql_search_document could not be refreshed."""


class RetrievalError(GenqlError):
    """Hybrid retrieval or reranking could not complete. Runs online, not during discovery."""
