# GenQL Phase 7 — Optimizer

## 1. Purpose

The parent spec's §11 states the thesis directly: "correct SQL that cannot execute affordably is not
correct enough." This phase builds the three sub-phases §11 names — pre-execution static rewrite,
pre-execution cost-gated decomposition, and post-execution learned recording — plus the index
recommendations the third sub-phase feeds. It inserts between Phase 6.5's `CANDIDATE_SELECTION`
(produces `validated_sql: str`) and Phase 5's `GUARDED_EXECUTION`, and adds one best-effort step after
execution.

**Scope, decided explicitly:**

- **Static rewrite is single-pass, registration-order, not a fixpoint loop.** `RewriteRuleRegistry`'s
  four initial rules (§5's table: `predicate_pushdown`, `redundant_join_elimination`,
  `cte_materialization`, `projection_pruning`) each take a sqlglot `Expression` and return a
  (possibly identical) `Expression` — never `None`, never raising. Running each rule once in
  registration order, rather than iterating to a fixpoint, is a deliberate simplicity choice: a
  fixpoint loop needs its own termination argument, and four independent, non-conflicting AST
  transforms converge in one pass by construction (none of them re-creates a pattern another one
  removes). A rule that later needs iteration registers its own internal loop; the registry stays a
  flat one-pass pipeline.
- **The cost gate never executes an over-budget query, even after rewriting.** Per §11: "queries that
  remain over budget after rewriting return an explanation and a suggested narrowing rather than
  executing." One rewrite pass, one `EXPLAIN (FORMAT JSON)` estimate, and — only if still over budget
  — exactly one LLM-driven decomposition attempt, then one more estimate. A query still over budget
  after that returns a typed, non-executing result. This is the same governance instinct as "GenQL
  never creates an index itself": the system explains and suggests, it does not act unilaterally on
  the user's behalf when the safe default is disclosure.
- **Post-execution recording is opt-in, because it doubles the query's cost.** `EXPLAIN (ANALYZE,
  BUFFERS)` actually re-runs the statement — recording actuals for every turn would silently double
  warehouse load for a purely diagnostic feature. `Settings.record_execution_actuals` (default
  `False`) gates it; when off, the turn behaves exactly as Phase 6.5 left it. This is the same
  demand-driven instinct §20 established for the ambiguity machinery, applied to a feature whose cost
  is a full second query rather than one more model call.
- **Index recommendations are a CLI report, not scheduled automation.** No scheduler infrastructure
  exists in this codebase yet, and the parent spec is explicit that GenQL "never creates an index
  itself." `genql optimizer recommend-indexes` reads accumulated evidence on demand and prints a
  ranked list for a human to act on.
- **Rewrite-rule equivalence testing is a small in-phase fixture set, not the full golden-set
  runner.** §17's testing strategy calls for "hypothesis asserts ... each rewrite rule preserves
  results on the golden set," but the golden-set *runner* (a CLI command, YAML fixture loader, and
  order-insensitive result comparison utility) is Phase 8 scope per §15. This phase writes four to six
  hand-picked question/SQL fixtures directly in its own test module and asserts execution-result
  equality before and after each rewrite rule runs, against real `local.tpcds`. Phase 8 generalizes
  this into the full golden-set runner and reuses the same fixtures rather than inventing new ones —
  avoiding both a circular phase dependency and duplicate fixture authoring.

**What this phase does not touch:** the ambiguity machinery (Phase 6.5, unchanged upstream), the
API/SSE layer, the full golden-set runner, and the ablation harness (Phase 8).

---

## 2. Domain

New entities (`genql/domain/entities/`):

```python
# domain/entities/optimization_result.py
class OptimizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str  # possibly rewritten, possibly decomposed
    rules_applied: tuple[str, ...]  # names of RewriteRules that actually changed the AST
    estimated_cost: float  # EXPLAIN (FORMAT JSON) Total Cost, after the final rewrite attempt
    within_budget: bool
    narrowing_suggestion: str | None  # set only when within_budget is False

# domain/entities/rewrite_outcome.py
class RewriteOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql_hash: str  # sha256 of the executed statement, the natural key for later aggregation
    datasource_name: str
    rules_applied: tuple[str, ...]
    estimated_cost: float
    actual_total_time_ms: float
    actual_rows: int
    shared_buffers_hit: int
    shared_buffers_read: int

# domain/entities/index_recommendation.py
class IndexRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    object_qualified_name: str
    column_name: str
    rationale: str  # e.g. "3 of 3 recorded executions filtered this column via sequential scan"
    supporting_execution_count: int
```

New ports (`genql/domain/ports/`):

```python
# domain/ports/rewrite_rule.py
class RewriteRule(Protocol):
    """A pure, semantics-preserving sqlglot AST transform. Returns the
    expression unchanged when the rule does not apply — never None, never a
    side effect — so `OptimizationService` can always compare identity to
    know whether a rule fired, for `rules_applied`."""
    name: str
    def apply(self, expression: exp.Expression) -> exp.Expression: ...

# domain/ports/cost_estimator.py
class CostEstimator(Protocol):
    def estimate(self, sql: str, datasource_name: str) -> float: ...

# domain/ports/query_decomposer.py
class QueryDecomposer(Protocol):
    """One grounded LLM call, following PlanningService's exact pattern:
    given the plan, the over-budget SQL, and the cost gap, returns a
    simplified statement (e.g. a narrower date range, a pushed-down filter
    the static rules could not prove safe on their own)."""
    def decompose(self, plan: QueryPlan, sql: str, estimated_cost: float, budget: float) -> str: ...

# domain/ports/rewrite_outcome_writer.py
class RewriteOutcomeWriter(Protocol):
    def write(self, outcome: RewriteOutcome) -> None: ...

# domain/ports/index_recommender.py
class IndexRecommender(Protocol):
    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]: ...
```

`QueryState` (`genql/api/query_state.py`) gains: `optimization: OptimizationResult | None`.

`TurnResponse` (`genql/domain/entities/turn_response.py`) gains: `narrowing_suggestion: str | None` —
set, alongside a `None` `result`, exactly when the turn ends because a query stayed over budget.

---

## 3. Registries

**New: `REWRITE_RULES: Registry[RewriteRule]`**, in `genql/repositories/query/registry.py` alongside
`CANDIDATE_STRATEGIES` (Phase 6.5). Four initial registrations, one file each under
`genql/repositories/query/rewrite_rules/`:

- `predicate_pushdown` — pushes a `WHERE` predicate on a joined table down past the join where
  sqlglot's own predicate-pushdown optimizer module proves it safe.
- `redundant_join_elimination` — removes a joined table whose columns are never referenced and whose
  join is provably not filtering (an FK-to-PK join with no `WHERE` clause touching it), using the
  join-path metadata already available from `SchemaLink`.
- `cte_materialization` — wraps a repeated subquery referenced more than once in the same statement in
  a `WITH` CTE, so the planner does not re-evaluate it.
- `projection_pruning` — expands a bare `SELECT *` against a known object into its actual column list
  from `SchemaLink.column_names`, and drops selected columns nothing downstream (the outer query, if
  any) references.

`OptimizationService` calls `REWRITE_RULES.all()` in registration order. Adding a fifth rule is one
new file plus one decorator, per the project's registry convention — no change to
`OptimizationService`.

---

## 4. Infrastructure

**Migration `0009_rewrite_outcomes.py`:**

```sql
CREATE TABLE genql_rewrite_outcome (
    id BIGSERIAL PRIMARY KEY,
    sql_hash TEXT NOT NULL,
    datasource_id BIGINT NOT NULL REFERENCES genql_datasource(id) ON DELETE CASCADE,
    rules_applied TEXT[] NOT NULL,
    estimated_cost DOUBLE PRECISION NOT NULL,
    actual_total_time_ms DOUBLE PRECISION NOT NULL,
    actual_rows BIGINT NOT NULL,
    shared_buffers_hit BIGINT NOT NULL,
    shared_buffers_read BIGINT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX genql_rewrite_outcome_datasource_idx ON genql_rewrite_outcome (datasource_id);
```

**`Settings` gains** (`genql/core/settings.py`):

```python
# Postgres planner cost units (arbitrary, not wall-clock) from EXPLAIN's Total
# Cost. A rough proxy until Phase 8's golden/ablation harness can correlate it
# against real wall-clock time on this specific warehouse.
cost_budget: float = 100_000.0
record_execution_actuals: bool = False
```

---

## 5. Repositories

```python
# repositories/query/cost_estimator_repository.py
class PostgresCostEstimator:  # CostEstimator
    """`EXPLAIN (FORMAT JSON) <sql>` through the same read-only engine
    binding GuardedExecutionService uses — EXPLAIN without ANALYZE never
    executes the statement, so this is as safe as static validation, not as
    risky as guarded execution."""
    ...

# repositories/query/rewrite_outcome_repository.py
class PostgresRewriteOutcomeWriter:  # RewriteOutcomeWriter, plain insert
    ...
class PostgresIndexRecommender:  # IndexRecommender
    """Aggregates genql_rewrite_outcome by (datasource, referenced column)
    joined against sqlglot's own parse of each recorded sql_hash's original
    statement to recover which columns were filtered, surfacing columns with
    repeated high-buffer-read executions and no supporting index (checked
    against genql_column's existing index metadata from Phase 2's catalog
    scan)."""
    ...
```

---

## 6. Services

New, under `genql/services/query/`:

- **`OptimizationService`** — `optimize(plan, sql, datasource_name) -> OptimizationResult`. Parses
  `sql` once with sqlglot, applies every `REWRITE_RULES` entry in order, renders the result, estimates
  cost via `CostEstimator`. If `estimated_cost <= Settings.cost_budget`, returns
  `within_budget=True`. Otherwise calls `QueryDecomposer.decompose` once, re-estimates the decomposed
  SQL, and returns whichever of the two estimates is lower — `within_budget` reflects that final
  number, and `narrowing_suggestion` is populated (a short, model-free string built from the gap
  between final cost and budget, e.g. "narrow the date range or add a filter — estimated cost is Nx
  the configured budget") only when still over budget.
- **`RewriteOutcomeRecordingService`** — `record(sql, rules_applied, estimated_cost,
  datasource_name) -> None`, called only when `Settings.record_execution_actuals` is true. Runs
  `EXPLAIN (ANALYZE, BUFFERS)` through the same `CostEstimator`-adjacent repository path (a second
  method on the same repository, since both are EXPLAIN variants against the same binding), builds a
  `RewriteOutcome`, and writes it. Wrapped in a `try/except` at the call site (§7) that logs and
  swallows any failure — this step is diagnostic, and its failure must never fail a turn whose actual
  query already executed successfully.
- **`IndexRecommendationService`** — thin wrapper: `recommend(datasource_name) ->
  tuple[IndexRecommendation, ...]`, delegating to `IndexRecommender`. Exists as a service (rather than
  the CLI calling the port directly) only to keep the "controllers never hold business logic" rule
  intact for the one line of logic it has (sorting by `supporting_execution_count` descending).

---

## 7. Controller: graph extension and CLI

`genql/api/query_graph.py` gains one node, inserted between `CANDIDATE_SELECTION` (Phase 6.5) and
`GUARDED_EXECUTION` (Phase 5):

```
CANDIDATE_SELECTION → REWRITE_AND_COST_GATE ─┬─(within_budget)──→ GUARDED_EXECUTION
                                              └─(over_budget)────→ END (narrowing_suggestion set)
```

`GuardedExecutionNode` (Phase 5) gains one optional constructor parameter,
`recorder: RewriteOutcomeRecordingService | None`, defaulting to `None` when
`Settings.record_execution_actuals` is false — composition root simply does not construct one, so the
node's post-execution call is `if self._recorder is not None: self._recorder.record(...)` guarded by
its own `try/except`, per §6. This keeps the disabled-by-default path a single `is not None` check
rather than a second conditional edge in the graph.

`genql/cli/commands/optimizer.py` (new file, new `genql optimizer` command group):

```
genql optimizer recommend-indexes --datasource X
    → prints a ranked table of IndexRecommendation rows, or "no recommendations
      yet — record_execution_actuals is off or no executions are recorded"
```

---

## 8. Configuration

Covered in §4: `cost_budget`, `record_execution_actuals`.

---

## 9. Testing

**Unit** — `OptimizationService` against a fake `REWRITE_RULES` registry entry and a fake
`CostEstimator`/`QueryDecomposer`, covering: within-budget-after-static-rewrite (no decomposer call),
over-budget-then-decomposition-succeeds, and over-budget-after-decomposition (returns
`narrowing_suggestion`, never raises). Each of the four real rewrite rules gets its own unit test
against a small hand-built sqlglot `Expression`, asserting the specific transform and asserting a
no-op on inputs the rule should not touch. `IndexRecommendationService`'s sort order against fake
`IndexRecommender` output.

**Property** — the four to six golden fixtures named in §1, each executed against real `local.tpcds`
before and after every individual rewrite rule (isolated, one rule at a time, not the full pipeline),
asserting order-insensitive result-set equality. This is the "hypothesis asserts ... preserves results
on the golden set" property from §17, scaled to what this phase alone can build.

**Integration (testcontainers)** — migration `0009` upgrade/downgrade; `PostgresCostEstimator` against
real `local.tpcds` (asserting a `SELECT *` on the largest fact table estimates a materially higher
cost than the same query with a `LIMIT`); `PostgresRewriteOutcomeWriter` round trip.

**Real-provider integration (gated)** — one real `QueryDecomposer.decompose` call, skipped without
`GENQL_OPENROUTER_API_KEY`.

**End-to-end** — a deliberately expensive question against `local.tpcds` (an unfiltered cross-fact
join) is asserted to return a `narrowing_suggestion` and no executed result when `cost_budget` is set
low in the test's `Settings`; the same question with a realistic default budget executes normally.

---

## 10. Consequences for later phases

**Phase 8 (API and evaluation)** generalizes this phase's four-to-six hand-picked fixtures into the
full golden-set runner (§15) and reuses them rather than re-authoring; it is also where
`cost_budget`'s planner-cost-unit proxy finally gets checked against measured wall-clock accuracy via
the ablation harness, and where `record_execution_actuals` traffic — once real users start opting
into it, or once the golden-set runner opts it on for its own runs — starts giving
`IndexRecommendationService` something non-trivial to report on a fresh installation.

---

## 11. Risks

**`cost_budget` is a planner-estimate proxy, not a latency guarantee.** PostgreSQL's `EXPLAIN` cost
units are internal and only loosely correlated with wall-clock time across different hardware and
cache states. Mitigation: documented as a rough, tunable proxy rather than a promise; Phase 8's
ablation harness is where this gets checked against reality, matching the same "flag the gap, don't
hide it" posture Phase 6.5 took for its own unmeasured cost-model assumptions.

**A rewrite rule that is not actually semantics-preserving corrupts results silently, and only four to
six fixtures cover it before Phase 8.** Mitigation: each rule is small, individually tested, and the
registry means a suspect rule can be unregistered (commented out of the registration import) without
touching `OptimizationService`, which is the whole point of the registry design — containment, not
just extensibility.

**`redundant_join_elimination`'s "provably not filtering" check is only as good as the join-path and
FK metadata Phase 3's graph projection produced.** A join wrongly judged non-filtering would change
result cardinality, which is exactly the class of bug the property tests in §9 exist to catch before
it reaches a real turn — but only for the objects the fixture set actually covers. Mitigation: this
rule is the first one exercised in the fixture set, and is the rule most worth expanding fixture
coverage for once Phase 8's golden set is larger than six questions.
