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
    # Empty by default, same pattern as openrouter_api_key — only required
    # once a chat_provider/embedding_provider setting actually selects "openai".
    openai_api_key: str = ""
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
    # The Fernet key that warehouse passwords are encrypted under. Empty by
    # default for the same reason as readonly_db_password — `migrations/env.py`
    # and every container unit test construct Settings() without one — and the
    # typed failure (MissingEncryptionKeyError) is raised at the point a
    # credential is actually written or read. Rotating it makes every stored
    # credential unreadable, so it belongs in the deployment's secret store,
    # not in a .env someone regenerates.
    secret_key: str = ""
    # YAML rule defaults for the ambiguity gate. Off: the two rules shipped in
    # `semantic/local.yaml` silently bound every question to "the most recent
    # complete calendar year", which is how a plain "top 10 stores by sales"
    # acquired a date predicate nobody asked for — and, against a star schema
    # whose date column is a surrogate key, an invalid one. Rules are a real
    # feature and the machinery is intact; they are disabled until a question
    # actually needs one, at which point this flips back to True.
    rules_enabled: bool = False
    # Below this per-dimension confidence, the gate treats the dimension as
    # unspecified and asks about it. Originally 0.7, reasoned as "a wrong
    # assumption costs a whole wasted pipeline run, while an unnecessary
    # question costs one round trip" — live testing showed the round-trip cost
    # was badly underestimated (12-14s plus a human, and in `genql eval golden`
    # an unwanted clarification is scored as an outright failure, not a cheap
    # retry), and at 0.7 every tested question triggered at least one
    # clarification. 0.55 is an interim tightening, not a calibrated value:
    # combined with AmbiguityGateService's schema-aware time_range filter (the
    # bigger fix — it removes a whole class of question from being scored at
    # all rather than hoping the threshold catches it), re-run
    # `genql eval golden` after deploying both changes and adjust from there.
    ambiguity_threshold: float = 0.55
    # How many clarifying questions ONE turn may ask before the gate stops
    # asking and starts assuming. Past the cap, every still-under-threshold
    # dimension is carried to the planner as an explicit assumption and
    # reported back to the user, who corrects a visible decision after seeing
    # an answer instead of answering an interview before seeing one.
    #
    # 1, because the observed complaint was three questions in a row on a
    # single question ("what time period?", then "what income threshold?",
    # then "what comparison baseline?") — each one a full round trip plus a
    # human, on a turn that had not yet returned a row. The termination proof
    # was never the problem: six dimensions resolved one per round always
    # terminated, it just terminated in six rounds. None disables the budget
    # and restores unlimited asking.
    ambiguity_max_questions: int | None = 1
    # How many distinct dimensions the USER must have answered before a turn
    # counts as "contested" and pays for multi-candidate generation,
    # critique, and probing. Rule defaults are deliberately not counted (see
    # AmbiguityGateNode): a YAML default is a pre-answered dimension, and
    # counting it made every turn against a datasource with any rules at all
    # contested before the user typed a word. Phase 6.5's
    # original definition used 1 — any resolution at all — which live testing
    # showed made contested the common case rather than the exception:
    # almost every question against a sales-shaped schema needs one
    # time_range clarification. 2 restores "contested" to mean a question
    # that was unclear along multiple axes at once, which is the actual
    # signal that a single generated candidate might guess wrong on some
    # OTHER dimension critique and probing exist to catch — not proof that
    # any clarification happened. Re-run `genql eval golden` before changing
    # this further; accuracy is the reason the floor is 2, not 1.
    contested_min_resolved_dimensions: int = 2
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
    # OpenAI's `reasoning_effort` param (low/medium/high), applied only to the
    # escalation model and only when chat_provider is "openai" — since this
    # deployment's escalation model is the *same* model as the primary
    # (chat_model_escalation == chat_model, a stopgap forced by billing, not
    # architecture), the only way left to make escalation genuinely stronger
    # than the first attempt is to spend more reasoning on the retry. None
    # (the default) leaves ChatOpenAI's own default in place, and the field
    # is silently ignored by every other provider (OpenRouter's chat
    # completions endpoint has no equivalent parameter).
    chat_model_escalation_reasoning_effort: str | None = None
    # Caps AmbiguityProbingService regardless of how many dimensions a
    # critique disagreement touches, bounding worst-case probing latency and
    # cost per the spec's §19 risk mitigation.
    probing_max_probes: int = 3
    # When critique's top-scoring surviving candidate beats the runner-up by
    # at least this much (both on critique's 0.0-1.0 score), AmbiguityProbingNode
    # skips probing entirely rather than spending a designer call plus one
    # execution per probe to confirm what critique's own score already shows
    # clearly. CandidateSelectionService already treats an empty probe_results
    # tuple as "fall through to critique_ranked", so this changes nothing about
    # correctness on the skip path — it removes work that would have reached
    # the same selection. 0.3 is conservative: a two-candidate critique score
    # spread that wide is a strong signal, not a close call. Lower it only
    # after confirming on real turns that a wider margin still selects the
    # same candidate probing would have.
    probing_skip_margin: float = 0.3
    # How many offline synthetic ambiguity examples the contested generation
    # path retrieves as few-shot context. Small on purpose: these are
    # few-shot exemplars, not a retrieval corpus to page through.
    ambiguity_example_top_k: int = 3
    # PostgreSQL planner cost units (arbitrary, not wall-clock) read from
    # EXPLAIN's Total Cost. A rough proxy until Phase 8's ablation harness can
    # correlate it against measured time on this specific warehouse.
    #
    # 100_000 (this setting's original default) proved too tight in practice:
    # a correct, already-rewritten three-fact-table UNION SUM against the
    # TPC-DS SF1 golden warehouse — about as small a "real" query as this
    # system answers — estimated at roughly 2x that budget and was refused.
    # 300_000 is a documented interim widening, not a calibrated number; it
    # trades a little more protection against a truly runaway plan for not
    # refusing ordinary full-table aggregates on a small warehouse. Re-tune
    # once Phase 8's harness can correlate estimated cost against measured
    # time on real warehouse sizes.
    #
    # Widening the budget is preferred over adding a LIMIT to reduce the
    # estimated cost: QueryDecomposer (query_decomposer.py) already refuses to
    # add one for exactly this reason — an aggregate like SUM/COUNT must scan
    # every row that belongs in it, so a LIMIT on the query would return a
    # partial, silently wrong total rather than a cheaper true one. Only a
    # row-returning (non-aggregate) statement could safely take a LIMIT, and
    # GuardedExecutionService already caps every executed statement's *result
    # set* at `query_row_cap` regardless — that guardrail is about the size of
    # the answer sent back, not the cost of computing it, and does not help a
    # query that fails the pre-execution cost gate at all.
    cost_budget: float = 300_000.0
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
    # Comma-separated origins allowed to call this API directly from
    # client-side JavaScript (the Phase 9b frontend). Empty by default —
    # same pattern as every other required-at-use secret in this file —
    # so no origin is trusted until explicitly configured.
    cors_allowed_origins: str = ""
    # Where `semantic overlay` and the ingestion pipeline look for
    # hand-written `<datasource>.yaml` overrides.
    semantic_overlay_dir: str = "semantic"
    # How long the ingestion worker waits before asking the queue again when
    # it found nothing. A tick that DID find work never waits, so this only
    # bounds how stale an idle queue can be.
    ingestion_poll_seconds: float = 1.0
    # A job still marked RUNNING with no progress for this long is assumed to
    # belong to a worker that died, and is returned to the queue. Must exceed
    # the slowest single step — profiling a large warehouse — or a live run
    # gets claimed a second time.
    ingestion_stale_after_seconds: int = 900
