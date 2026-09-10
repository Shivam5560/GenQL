"""Typed failures. Every stage returns one of these so callers can route.

Split into per-area modules because the flat file hit the repository's
250-line-per-file limit; every name below is re-exported here so every
existing `from genql.domain.errors import X` keeps working untouched.
"""

from __future__ import annotations

from genql.domain.errors.auth import InvalidAccessTokenError
from genql.domain.errors.base import GenqlError
from genql.domain.errors.datasource import (
    AmbiguousScopeError,
    DatasourceError,
    DuplicateDatasourceError,
    EmptySchemaError,
    IncompleteDatasourceConnectionError,
    MissingDatasourceSecretError,
    MissingEncryptionKeyError,
    MissingReadonlySecretError,
    UndecryptableDatasourceSecretError,
    UnknownDatasourceError,
    UnknownSchemaRegistrationError,
)
from genql.domain.errors.discovery import (
    AmbiguityExampleGenerationError,
    CatalogAccessError,
    CompileError,
    DiscoveryError,
    DomainNamingError,
    EnrichmentError,
    GraphAnalysisError,
    GraphProjectionError,
    OverlayError,
    ProfilingError,
    UnknownDiscoveryStepError,
)
from genql.domain.errors.eval import (
    EvaluationError,
    FeedbackError,
    GoldenSetError,
    UnknownAblationError,
)
from genql.domain.errors.ingestion import (
    IngestionError,
    IngestionInProgressError,
    NoIngestionJobError,
    UnknownIngestionJobError,
    UnknownIngestionStepError,
)
from genql.domain.errors.provider import (
    ChatProviderError,
    EmbeddingProviderError,
    RerankProviderError,
    RetrievalError,
)
from genql.domain.errors.query import (
    AmbiguityGateError,
    CostEstimationError,
    CritiqueError,
    DomainScopingError,
    ExecutionError,
    GenerationError,
    IntentClassificationError,
    OptimizationError,
    PlanningError,
    QueryError,
    SchemaLinkingError,
    StaticValidationError,
    ThreadLockError,
    UnknownThreadError,
)
from genql.domain.errors.thread_history import ThreadOwnershipError

__all__ = [
    "GenqlError",
    "InvalidAccessTokenError",
    "ThreadOwnershipError",
    "DiscoveryError",
    "CatalogAccessError",
    "ProfilingError",
    "UnknownDiscoveryStepError",
    "GraphProjectionError",
    "GraphAnalysisError",
    "EnrichmentError",
    "DomainNamingError",
    "OverlayError",
    "CompileError",
    "AmbiguityExampleGenerationError",
    "DatasourceError",
    "UnknownDatasourceError",
    "DuplicateDatasourceError",
    "MissingDatasourceSecretError",
    "MissingEncryptionKeyError",
    "UndecryptableDatasourceSecretError",
    "EmptySchemaError",
    "IncompleteDatasourceConnectionError",
    "UnknownSchemaRegistrationError",
    "AmbiguousScopeError",
    "MissingReadonlySecretError",
    "IngestionError",
    "UnknownIngestionJobError",
    "NoIngestionJobError",
    "IngestionInProgressError",
    "UnknownIngestionStepError",
    "ChatProviderError",
    "EmbeddingProviderError",
    "RerankProviderError",
    "RetrievalError",
    "QueryError",
    "SchemaLinkingError",
    "PlanningError",
    "GenerationError",
    "StaticValidationError",
    "ExecutionError",
    "IntentClassificationError",
    "AmbiguityGateError",
    "DomainScopingError",
    "ThreadLockError",
    "CritiqueError",
    "UnknownThreadError",
    "OptimizationError",
    "CostEstimationError",
    "EvaluationError",
    "GoldenSetError",
    "UnknownAblationError",
    "FeedbackError",
]
