"""Process configuration, read once from the environment.

`warehouse_dsn` is deliberately absent: it described a single warehouse, which
is exactly the assumption Phase 2.5 deletes. The value lives on as the
environment variable that the `local` datasource row names. `semantic_dsn`
stays, because GenQL's own store genuinely is singular.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GENQL_", env_file=".env", extra="ignore")

    semantic_dsn: str
    default_datasource: str | None = None
    scope_resolver: str = "default"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "genqlgenql"
    profile_sample_limit: int = 5
    clustering_algorithm: str = "leiden"
    node_embedding_algorithm: str = "fastrp"
    join_path_strategy: str = "weighted_shortest_path"
    max_join_path_hops: int = 4
    openrouter_api_key: str = ""
    cohere_api_key: str | None = None
    chat_provider: str = "openrouter"
    embedding_provider: str = "openrouter"
    rerank_provider: str = "openrouter"
    rerank_enabled: bool = True
    chat_model: str = "anthropic/claude-sonnet-5"
    embedding_model: str = "openai/text-embedding-3-small"
    rerank_model: str = "cohere/rerank-4-pro"
    domain_clustering_algorithm: str = "fused"
    domain_cluster_k_min: int = 2
    domain_cluster_k_max: int = 20
    retriever: str = "hybrid_rrf"
    rrf_k: int = 60
    search_top_k: int = 10
    query_row_cap: int = 1000
    query_statement_timeout_ms: int = 30_000
    # Empty by default rather than required: `migrations/env.py` and every
    # container unit test construct Settings() without it, and the house
    # pattern for a required-at-use-time secret is exactly openrouter_api_key's
    # — default empty, typed error at the point of use.
    readonly_db_password: str = ""
