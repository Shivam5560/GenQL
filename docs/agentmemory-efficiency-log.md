# agentmemory efficiency log

Tracks whether handing a session off through the `agentmemory` plugin (save state → new session →
`memory_recall`/`memory_smart_search`) actually reduces token/tool-call cost versus re-deriving
context from the repo and prior conversation. One entry per handoff. Be honest about partial or
failed recalls — the point of this log is to let a later review answer, with evidence, whether the
practice is worth keeping.

**Efficiency % definition (working definition, refine if a better one emerges):**
`100 * (1 - (tool calls spent re-deriving context after recall) / (estimated tool calls a from-
scratch re-derivation of the same context would have cost))`. A recall that fully resumed the task
with zero re-exploration scores 100%; a recall that turned out irrelevant and required full
re-derivation anyway scores 0%.

| Date | Session / task | Memories saved (project) | Recalled successfully? | Re-derivation needed after recall | Efficiency % | Notes |
|---|---|---|---|---|---|---|
| 2026-09-06 | GenQL Phase 4 design (this session, pre-handoff) | 5 entries saved to project `genql`: Phase 4 scope, schema, ports/registries, CLI/service shape, Phase 3 closure status | n/a — no handoff has occurred yet in this session | n/a | n/a | Baseline row only, recording what was saved. First real efficiency measurement happens at the next actual handoff, once a fresh session recalls these and we can compare against what re-deriving them would have cost (this session's own exploration took roughly a dozen file reads plus two full spec documents to arrive at these decisions). |
