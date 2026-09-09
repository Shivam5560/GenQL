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
    # Below this per-dimension confidence, the gate treats the dimension as
    # unspecified and asks about it. 0.7 rather than 0.5 because a wrong
    # assumption costs a whole wasted pipeline run, while an unnecessary
    # question costs one round trip.
    ambiguity_threshold: float = 0.7
    # How many retrieval hits the plurality vote is taken over. Larger than
    # search_top_k (10) on purpose: scoping wants a broad sample of which
    # domains the question touches, not the best ten objects.
    domain_scoping_sample_size: int = 20
    # PostgresSaver's own pool, separate from the SQLAlchemy engine pool and
    # from the advisory lock's dedicated connection. Small because a CLI turn
    # is single-threaded; an API server would raise it.
    checkpoint_pool_max_size: int = 4
    # Used only for the one escalated regeneration this phase allows, when
    # every surviving candidate carries a fatal defect after one repair round.
    # A distinct, stronger model rather than a retry against chat_model: the
    # parent spec's §20 names Opus specifically for this trigger.
    chat_model_escalation: str = "anthropic/claude-opus-5"
    # Caps AmbiguityProbingService regardless of how many dimensions a
    # critique disagreement touches, bounding worst-case probing latency and
    # cost per the spec's §19 risk mitigation.
    probing_max_probes: int = 3
    # How many offline synthetic ambiguity examples the contested generation
    # path retrieves as few-shot context. Small on purpose: these are
    # few-shot exemplars, not a retrieval corpus to page through.
    ambiguity_example_top_k: int = 3
    # PostgreSQL planner cost units (arbitrary, not wall-clock) read from
    # EXPLAIN's Total Cost. A rough proxy until Phase 8's ablation harness can
    # correlate it against measured time on this specific warehouse.
    cost_budget: float = 100_000.0
    # Off by default because EXPLAIN (ANALYZE, BUFFERS) re-runs the statement:
    # recording actuals for every turn would silently double warehouse load
    # for a purely diagnostic feature.
    record_execution_actuals: bool = False
    # Ablation switches. All True in normal operation. Only the ablation
    # harness sets one False, and it does so through Container.with_overrides
    # rather than the environment — deliberately absent from .env.example,
    # because a stray GENQL_ENRICHMENT_ENABLED=false would silently degrade
    # every real turn with nothing in the output to say so.
    enrichment_enabled: bool = True
    domain_scoping_enabled: bool = True
    join_paths_enabled: bool = True
    probing_enabled: bool = True
    ambiguity_examples_enabled: bool = True

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Where `genql eval` looks for *.yaml fixtures.
    golden_set_dir: str = "golden"
    # Must exactly match docker/compose.yaml's gotrue service's
    # GOTRUE_JWT_SECRET — GoTrue signs access tokens with it, GoTrueJwtVerifier
    # verifies with it. Empty by default so Settings() still constructs in
    # every test and CLI path that never touches auth, matching the
    # readonly_db_password pattern: a typed error at first use, not at import.
    gotrue_jwt_secret: str = ""
