"""Typed failures. Every stage returns one of these so callers can route."""

from __future__ import annotations

from genql.domain.entities.guardrail_violation import GuardrailViolation


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


class MissingReadonlySecretError(DatasourceError):
    """GENQL_READONLY_DB_PASSWORD is unset, so no read-only engine can be built.

    Separate from MissingDatasourceSecretError: that one means a datasource's
    own DSN variable is missing, this one means the process-wide read-only
    role password is, and the fix is different in each case.
    """

    def __init__(self, datasource_name: str) -> None:
        super().__init__(
            f"no read-only engine can be built for datasource {datasource_name!r}: "
            "GENQL_READONLY_DB_PASSWORD is unset or empty"
        )
        self.datasource_name = datasource_name


class QueryError(GenqlError):
    """The online query pipeline could not produce an answer.

    Runs online, not during discovery, so it hangs off GenqlError rather than
    DiscoveryError — same placement rule RetrievalError follows.
    """


class SchemaLinkingError(QueryError):
    """Retrieval returned nothing usable for this question."""


class PlanningError(QueryError):
    """The planner could not produce a valid QueryPlan."""


class GenerationError(QueryError):
    """The candidate generator could not produce a valid SqlCandidate."""


class StaticValidationError(QueryError):
    """A candidate failed one or more guardrails and could not be repaired.

    Carries the violations rather than only a message so the graph's retry
    edge can hand them back to candidate generation as feedback.
    """

    def __init__(self, violations: tuple[GuardrailViolation, ...]) -> None:
        detail = "; ".join(f"{v.rule_name}: {v.message}" for v in violations) or "no detail"
        super().__init__(f"static validation failed: {detail}")
        self.violations = violations


class ExecutionError(QueryError):
    """Guarded execution failed — timeout, permission denied, or a bad statement."""


class IntentClassificationError(QueryError):
    """The classifier returned something that is not a known question intent."""


class AmbiguityGateError(QueryError):
    """The ambiguity gate could not score the question's dimensions."""


class DomainScopingError(QueryError):
    """Domain scoping could not run at all.

    Distinct from "no domain resolved", which is a plain None return: this
    means the retrieval pass or the domain lookup itself failed, and the turn
    cannot continue with a silently unscoped search.
    """


class ThreadLockError(QueryError):
    """The per-thread advisory lock could not be acquired or released."""


class UnknownThreadError(QueryError):
    """`--thread-id` named a thread with no pending clarification to resume.

    Distinct from every checkpointed-but-wrong-answer case: this is what a
    thread id that was never checkpointed, already finished, or expired looks
    like from `resume_query`'s side, before the graph is invoked at all.
    """

    def __init__(self, thread_id: str) -> None:
        super().__init__(
            f"{thread_id!r} has no paused turn to resume: it is unknown, already "
            "finished, or its checkpoint has expired"
        )
        self.thread_id = thread_id
