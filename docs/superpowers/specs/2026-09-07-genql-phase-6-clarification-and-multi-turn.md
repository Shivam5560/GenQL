# GenQL Phase 6 — Clarification and Multi-Turn

## 1. Purpose

The parent spec's phasing (§18) names Phase 6 "Ambiguity machinery — critique, probing, selection,
synthetic ambiguity log, the LangGraph graph with the clarification interrupt and multi-turn
state." That bundles two only loosely related concerns: deciding *whether to ask* a clarifying
question at all, and *resolving disagreement* once multiple candidates exist. This spec covers only
the first — intent routing, the ambiguity gate, `genql_rule` defaults, and the LangGraph
`PostgresSaver`/`interrupt()`/advisory-lock plumbing that lets a turn pause and resume. Multi-candidate
generation, critique, probing, and data-driven selection move to **Phase 6.5**, because nothing
consumes candidate disagreement until critique exists, and because §20's demand-driven cost model
requires the gate to exist *first* — building the expensive multi-candidate path before anything can
decide when to skip it would leave that path permanently on. `genql_query_log`/`genql_query_feature`
and the query-weighted join-path strategy move further out, to Phase 8, where the golden-set runner
first generates real traffic for them to learn from; building them now produces tables nothing
populates yet.

**Scope, decided explicitly:**

- **Two new pipeline stages, prepended to Phase 5's graph.** `intent_classification` (parent spec §9
  stage 1) and `ambiguity_gate` (stage 2). A non-`analytical_sql` question short-circuits to a typed
  response without touching retrieval, planning, or execution — cheap, and it protects every
  downstream stage from questions they were never designed to answer.
- **`genql_rule` extends the existing YAML-overlay pattern, not a new CLI verb.** `genql_metric` is
  already YAML-authored, never LLM-guessed, always upserted, no merge step — `genql_rule` follows
  that exact precedent: a new `rules` list on `SemanticOverlay`, a `RuleWriter`, wired into the
  existing `SemanticOverlayService.apply` alongside metrics. `genql semantic overlay` picks up rules
  automatically; there is no separate `genql rule` command.
- **Domain scoping becomes a real pipeline stage (stage 3), not a manual flag.** Phase 5's
  `--domain-id` remains as an explicit override; when omitted, a new `DomainScopingService` runs an
  unscoped retrieval pass, picks the majority `domain_name` among the top hits, and resolves its id
  — the first real caller of Phase 4's `DomainScopedRetriever`, exactly as promised.
- **Multi-turn state is structured turn state, not chat history.** Per the parent spec's §13:
  resolved entities, the candidate metric, accepted defaults, rejected interpretations, and the
  current domain scope persist as `QueryState` through `PostgresSaver`, keyed by `thread_id`, guarded
  by a per-thread Postgres advisory lock. A resumed turn calls `interrupt()`'s answer back in through
  LangGraph's `Command(resume=...)` — it does not re-run intent classification or the ambiguity gate
  on the resumed input, since those already ran on the original question.
- **One clarifying question at a time, never a batch.** If the gate finds multiple missing
  dimensions, it asks about the single highest-priority one (fixed priority order: entity, metric,
  time range, grain, filter, comparison baseline) and re-assesses after each answer — matching the
  parent spec's "raises `interrupt()` with one targeted question," not a form.

**What this phase does not touch:** multi-candidate generation, critique, probing, data-driven
selection (Phase 6.5), rewrite/optimization (Phase 7), the API/SSE layer (Phase 8), and any
frequency-weighted join-path strategy (Phase 8, needs real query-log traffic).

---

## 2. Domain

New entities (`genql/domain/entities/`):

```python
# domain/entities/rule.py
@dataclass(frozen=True)
class Rule:
    """A YAML-authored default for one ambiguity-gate dimension. Never
    LLM-guessed, exactly like Metric."""
    name: str
    dimension: str  # one of AMBIGUITY_DIMENSIONS
    value: str  # e.g. "fiscal_year_to_date", "status = 'active'"
    description: str

# domain/entities/ambiguity_assessment.py
AMBIGUITY_DIMENSIONS: tuple[str, ...] = (
    "entity", "metric", "time_range", "grain", "filter", "comparison_baseline",
)

@dataclass(frozen=True)
class AmbiguityAssessment:
    is_ambiguous: bool
    missing_dimension: str | None  # highest-priority missing dimension, or None
    clarifying_question: str | None
    applied_defaults: tuple[tuple[str, str], ...]  # (dimension, rule_name) pairs actually used

# domain/entities/turn_response.py
@dataclass(frozen=True)
class TurnResponse:
    """What the CLI prints for one turn: either a paused clarification or a
    finished answer. Exactly one of `clarifying_question` / `result` is set."""
    thread_id: str
    clarifying_question: str | None
    intent: str | None  # set only on a non-analytical_sql short-circuit
    validated_sql: str | None
    result: ExecutionResult | None
    applied_defaults: tuple[tuple[str, str], ...]
```

New ports (`genql/domain/ports/`):

```python
# domain/ports/intent_classifier.py
class IntentClassifier(Protocol):
    def classify(self, question: str) -> str: ...  # one of QUESTION_INTENTS

# domain/ports/ambiguity_gate.py
class AmbiguityGate(Protocol):
    def assess(self, question: str, rules: tuple[Rule, ...]) -> AmbiguityAssessment: ...

# domain/ports/domain_scoper.py
class DomainScoper(Protocol):
    def resolve(self, question: str, datasource_name: str) -> int | None: ...

# domain/ports/rule_reader.py
class RuleReader(Protocol):
    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]: ...

# domain/ports/rule_writer.py
class RuleWriter(Protocol):
    def write_rules(self, datasource_name: str, rules: tuple[Rule, ...]) -> None: ...

# domain/ports/thread_lock.py
class ThreadLock(Protocol):
    """A context-manager-shaped port: acquire blocks until the advisory lock
    for this thread_id is held, release always runs. One thread, one
    in-flight turn — a second `genql query` on the same thread_id waits
    rather than corrupting checkpoint state."""
    def __enter__(self) -> None: ...
    def __exit__(self, *exc: object) -> None: ...
```

`QUESTION_INTENTS = ("analytical_sql", "metadata_question", "followup", "non_sql")` — a plain
tuple constant, not an enum registry, since nothing here registers a per-intent *implementation*;
only `analytical_sql` proceeds past `intent_classification`, and the other three all map to the
same "explain what you can't do yet" typed response.

`IntentClassifier` and `AmbiguityGate` both take the existing `ChatProvider` port, following the
exact grounded-call pattern `PlanningService` already established in Phase 5 — no new LLM port.

`QueryState` (`genql/api/query_state.py`) gains, additively:

```python
thread_id: str
intent: str | None
ambiguity: AmbiguityAssessment | None
```

---

## 3. Registries

No new registry. `RETRIEVERS` (Phase 4) and `GUARDRAILS` (Phase 5) are unaffected — domain scoping
calls the existing `domain_scoped`/default retriever directly through `RetrievalService`, it does not
add a new retriever kind.

---

## 4. Infrastructure

**New dependency:** `langgraph-checkpoint-postgres` (confirmed absent from `uv.lock` — base
`langgraph` only pulls the in-memory `langgraph-checkpoint`). `uv add langgraph-checkpoint-postgres`.

**Migration `0007_rules_and_checkpoints.py`:**

```sql
CREATE TABLE genql_rule (
    id BIGSERIAL PRIMARY KEY,
    datasource_id BIGINT NOT NULL REFERENCES genql_datasource(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    dimension TEXT NOT NULL,
    value TEXT NOT NULL,
    description TEXT NOT NULL,
    UNIQUE (datasource_id, name)
);
```

`PostgresSaver`'s own checkpoint tables (`checkpoints`, `checkpoint_writes`, etc.) are created by
`PostgresSaver.setup()`, called once from `genql/cli/main.py`'s startup path the same way the engine
provider already runs migrations lazily — not hand-written as an Alembic migration, since they are
langgraph's schema to own and evolve across its own releases, not this project's.

**Advisory lock:** a `PostgresThreadLock` in `genql/infrastructure/db/` opens a dedicated connection
(separate from the checkpointer's pool, since `pg_advisory_lock` is session-scoped) against GenQL's
own database — never the read-only warehouse binding — calling `pg_advisory_lock(hashtext(thread_id))`
on enter and `pg_advisory_unlock` on exit.

---

## 5. Repositories

```python
# repositories/semantic/rule_repository.py
class PostgresRuleReader:  # RuleReader
    ...
class PostgresRuleWriter:  # RuleWriter, upsert on (datasource_id, name)
    ...
```

Both follow `PostgresMetricRepository`'s exact shape from Phase 4 — same file organization, same
upsert-by-natural-key pattern.

`SemanticOverlay` (`genql/domain/entities/semantic_overlay.py`) gains:

```python
class RuleOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    dimension: str
    value: str
    description: str

# SemanticOverlay gains: rules: tuple[RuleOverlay, ...] = ()
```

`SemanticOverlayService.apply` gains a `rule_writer: RuleWriter` constructor parameter and, in
`apply`, an unconditional `self._rule_writer.write_rules(overlay.datasource, rules)` call — no
merge/`Enricher` involved, matching how metrics are already handled in that method today.

---

## 6. Services

New, under `genql/services/query/`:

- `IntentClassificationService` — one `ChatProvider.complete` call, returns one of
  `QUESTION_INTENTS`. Raises `IntentClassificationError` on a `ValidationError`.
- `AmbiguityGateService` — reads `genql_rule` via `RuleReader`, makes one `ChatProvider.complete`
  call scoring the six dimensions against the question, applies matching rules as defaults for any
  dimension a rule covers, and returns `AmbiguityAssessment`. Raises `AmbiguityGateError` likewise.
- `DomainScopingService` — wraps `RetrievalService.search` (unscoped, `top_k` from
  `Settings.domain_scoping_sample_size`) and `DomainRepository.by_name`, tallies `domain_name`
  across hits, and returns the id of the plurality domain, or `None` if the sample is empty or every
  hit lacks a domain. Raises nothing on ambiguity between domains — resolving the *wrong* domain here
  is not this phase's failure mode to solve; it is a plain best-effort default, same spirit as
  Phase 5's guardrail-repair-once policy: get it right most of the time, fail visibly downstream
  rather than silently, and leave real disambiguation to a later phase.

Modified: none of Phase 5's five services change signature. `SchemaLinkingService.link` already
takes `domain_id: int | None` — `domain_scoping`'s resolved value flows into the exact same
parameter Phase 5's manual `--domain-id` flag already filled.

---

## 7. Controller: graph extension, thread lock, and CLI

`genql/api/query_graph.py` gains two nodes and one new conditional edge, prepended to Phase 5's graph:

```
START → intent_classification ─┬─(non-analytical_sql)→ END (TurnResponse.intent set)
                                └─(analytical_sql)──────→ ambiguity_gate
ambiguity_gate ─┬─(is_ambiguous)──→ interrupt() → [pause] → (resume) → ambiguity_gate re-assessment
                └─(not ambiguous)─→ domain_scoping → schema_linking → … (Phase 5's existing graph, unchanged)
```

The re-assessment loop after a resumed answer is bounded by the same `AMBIGUITY_DIMENSIONS`
priority list running out — once every dimension the gate can name is either specified or defaulted,
`is_ambiguous` is structurally `False` on the next pass, so the loop provably terminates without a
retry counter (unlike Phase 5's guardrail loop, which needed one because guardrail rules do not
shrink a fixed list).

`genql/infrastructure/checkpoint/postgres_checkpointer.py` builds the `PostgresSaver` once at
composition-root construction (its own connection pool, wired from `Settings.database_url` — GenQL's
own database, never a datasource's warehouse).

`genql/cli/commands/query.py` gains `--thread-id TEXT` (optional):

```
genql query "<question>" --datasource X [--domain-id N]
    → new thread; if the gate interrupts, prints the generated thread_id and
      the clarifying question, exits 0 (a paused turn is not an error)
genql query "<answer>" --datasource X --thread-id <ID>
    → resumes thread <ID> via Command(resume=<answer>); the CLI does not
      re-validate --datasource against what the thread started with beyond
      what the checkpointer's own state naturally enforces
```

Both invocations acquire `ThreadLock` for the duration of the graph call and release it in a
`finally`, whether the call finishes, interrupts, or raises.

---

## 8. Configuration

`Settings` gains:

```python
ambiguity_threshold: float = 0.7
domain_scoping_sample_size: int = 20
database_url: str  # already implied by existing engine setup; named explicitly
                     # here because PostgresSaver needs it independent of any
                     # datasource's engine binding
```

---

## 9. Testing

**Unit** — `IntentClassificationService`, `AmbiguityGateService`, `DomainScopingService` against
fake `ChatProvider`/`RetrievalService`/`RuleReader` — no network, no database. A dedicated test
proves the re-assessment loop terminates: a fake `RuleReader` covering every dimension except one
must reach `is_ambiguous=False` after exactly one resumed answer for that one remaining dimension.
`SemanticOverlayService` gains a test asserting `rules` are written unconditionally (no merge), same
shape as its existing `metrics` test.

**Integration (testcontainers)** — migration `0007` upgrade/downgrade; `PostgresRuleReader`/
`PostgresRuleWriter` against real Postgres; `PostgresThreadLock` asserting a second acquire on the
same `thread_id` from a second connection blocks until the first releases; `PostgresSaver.setup()`
followed by one real interrupt-then-resume round trip against real Postgres, asserting the resumed
state matches what was checkpointed (no re-classification, no re-gating).

**Real-provider integration (gated)** — one real `IntentClassificationService.classify` and one real
`AmbiguityGateService.assess` call, skipped cleanly without `GENQL_OPENROUTER_API_KEY`, matching
every prior phase's convention.

**End-to-end** — `genql query "how many stores do we have"` (well-specified) against `local.tpcds`
answers directly, no interrupt, in one invocation. `genql query "show me revenue"` (missing time
range and grain) interrupts with a targeted question; the returned `thread_id` resumed with
`genql query "last quarter, by region" --thread-id <ID>` produces a validated SQL statement and
executed rows, proving the pause/resume round trip end to end.

---

## 10. Consequences for later phases

**Phase 6.5 (disagreement resolution)** upgrades `candidate_generation` to N candidates once
critique/probing exist to consume the disagreement, and its critique stage inherits this phase's
`AMBIGUITY_DIMENSIONS` vocabulary — stage 10's candidate-diff-to-dimension mapping reuses the exact
six names this phase establishes, rather than inventing a second taxonomy.

**Phase 7 (optimizer)** is unaffected structurally; it still inserts between `static_validation` and
`guarded_execution`, downstream of everything this phase adds.

**Phase 8 (API and evaluation)** exposes the interrupt/resume cycle over SSE (a paused turn becomes
a server-sent event carrying the clarifying question, not a synchronous HTTP response), and is where
`genql_query_log` and the frequency-weighted join-path strategy — deferred out of this phase, per
§1 — finally get real traffic to learn from via the golden-set runner.

---

## 11. Risks

**A wrongly-resolved domain silently narrows retrieval to the wrong slice of the schema.**
`DomainScopingService`'s plurality-vote heuristic has no confidence floor — a low-signal question
could tip toward the wrong domain as easily as the right one, and schema linking would then search
a scoped-but-wrong subset rather than failing loudly. Mitigation: this is explicitly a best-effort
default, not a decision the system commits to irreversibly — `--domain-id` remains a manual override
for exactly this failure mode, and real domain disambiguation (asking the user, or including domain
as a seventh ambiguity dimension) is deferred rather than half-built here.

**The advisory lock is per-process-connection, not per-cluster.** If GenQL ever runs as multiple
processes against the same Postgres (a future API server with several workers), two workers each
opening their own connection and calling `pg_advisory_lock` with the same key correctly block each
other at the database level — this is the standard, correct use of session-level advisory locks
across connections — but the lock is held only as long as that specific connection lives; a crashed
worker holding the lock releases it automatically when its connection drops (Postgres's own
guarantee), so no manual cleanup path is needed. Documented here because it is the first time this
codebase relies on connection-lifetime-scoped locking rather than transaction-scoped locking.

**`genql_rule`'s dimension-to-defaults mapping is a flat string match, not validated against
`AMBIGUITY_DIMENSIONS` at write time.** A YAML rule with a typo'd `dimension: "time_rnage"` is
silently never applied rather than rejected at `genql semantic overlay` time. Mitigation: this
follows the same "fail visibly downstream, not upfront" tradeoff Phase 4 already accepted for
`Metric.sql_expression` (a non-empty-string check, not a real parse) — closing this gap with a
`Literal[*AMBIGUITY_DIMENSIONS]` validator on `RuleOverlay.dimension` is a small, easy follow-up
once it proves worth doing, not a blocker for this phase.
