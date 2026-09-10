export interface DirectionStage {
  num: string
  short: string
  code: string
  label: string
  ms: string
  status: string
  summary: string
  note: string
  detail: [string, string][]
}

export const DIRECTION_STAGES: DirectionStage[] = [
  {
    num: "001",
    short: "INTENT",
    code: "intent_classification",
    label: "Intent",
    ms: "180 ms",
    status: "DONE",
    summary:
      "Sorts the sentence into a shape before anything touches your schema: an aggregate over a dimension, ranked, with a date floor.",
    note: "Classification is cheap and it narrows everything downstream. A misread here is the only failure the rest of the pipeline cannot correct.",
    detail: [
      ["class", "analytical_aggregate"],
      ["ranking", "top_k"],
      ["k", "5"],
      ["date floor", "2020-01-01"],
      ["confidence", "0.94"],
    ],
  },
  {
    num: "002",
    short: "DOMAIN",
    code: "domain_scoping",
    label: "Domain scoping",
    ms: "240 ms",
    status: "DONE",
    summary:
      "Picks the corner of the warehouse worth reading. One domain of six, so schema linking searches ten objects instead of four hundred.",
    note: "Scoping is what keeps the prompt small enough to be accurate on a real warehouse.",
    detail: [
      ["domains considered", "6"],
      ["selected", "retail_sales"],
      ["objects in scope", "10"],
      ["rejected", "web_analytics, hr"],
      ["cache", "warm"],
    ],
  },
  {
    num: "003",
    short: "SCHEMA",
    code: "schema_linking",
    label: "Schema linking",
    ms: "520 ms",
    status: "DONE",
    summary:
      "Binds every noun in your sentence to a real column, read live from the catalog — not from a model's memory of a schema.",
    note: "“Stores” resolved to tpcds.store.s_store_id; “states” to s_state. Both confirmed against the catalog scan, not guessed.",
    detail: [
      ["objects linked", "10"],
      ["columns bound", "4"],
      ["join paths found", "2"],
      ["catalog age", "4 min"],
      ["unresolved", "0"],
    ],
  },
  {
    num: "004",
    short: "GATE",
    code: "ambiguity_gate",
    label: "Ambiguity gate",
    ms: "610 ms",
    status: "PAUSED",
    summary:
      "Two readings of “distinct” survived scoping, so the pipeline stops and asks. One question, with the reading it would have picked shown as the default.",
    note: "“Distinct on stores, or on states?” — this is the stage that separates a query you can defend from a plausible one.",
    detail: [
      ["readings found", "2"],
      ["question budget", "1 of 2 used"],
      ["asked", "distinct dimension"],
      ["default offered", "stores"],
      ["answer", "stores"],
    ],
  },
  {
    num: "005",
    short: "PLAN",
    code: "planning",
    label: "Planning",
    ms: "380 ms",
    status: "DONE",
    summary:
      "Writes the shape of the statement before any SQL: which table is the grain, what the filter window is, how the count is taken.",
    note: "Single-table grain here, so no join path was needed — the plan says so explicitly rather than leaving it implied.",
    detail: [
      ["grain", "tpcds.store"],
      ["joins", "none required"],
      ["filter", "SCD window vs CURRENT_DATE"],
      ["aggregate", "COUNT DISTINCT"],
      ["order", "count desc, state asc"],
    ],
  },
  {
    num: "006",
    short: "DRAFTS",
    code: "candidate_generation",
    label: "Candidates",
    ms: "1.4 s",
    status: "DONE",
    summary:
      "Four independent drafts, deliberately different: two readings of the SCD date window, one with a subquery, one with a window function.",
    note: "Generating rivals is cheaper than trusting one draft. Three of these four are wrong in a way you would not have noticed.",
    detail: [
      ["candidates", "4"],
      ["strategy A", "SCD open-ended window"],
      ["strategy B", "rec_end_date IS NULL only"],
      ["strategy C", "subquery dedupe"],
      ["strategy D", "window function"],
    ],
  },
  {
    num: "007",
    short: "VALID",
    code: "static_validation",
    label: "Validation",
    ms: "290 ms",
    status: "DONE",
    summary:
      "Every candidate is parsed and dry-run against the live schema. Two failed here and never reached ranking.",
    note: "A statement that does not parse is not a candidate. This is the cheapest possible place to find that out.",
    detail: [
      ["parsed", "4 of 4"],
      ["dry run passed", "2 of 4"],
      ["D failed", "window fn not comparable"],
      ["C failed", "column ambiguity"],
      ["bind params", "guarded"],
    ],
  },
  {
    num: "008",
    short: "CRITIQUE",
    code: "critique",
    label: "Critique",
    ms: "980 ms",
    status: "DONE",
    summary:
      "The survivors are read back against your question and the linked schema, looking for the mistakes validation cannot see.",
    note: "“B silently drops historical rows — it only counts currently-open store records, which is not what ‘since 2020’ asks for.”",
    detail: [
      ["reviewed", "2"],
      ["issues on A", "0"],
      ["issues on B", "1 (semantic)"],
      ["severity", "high"],
      ["verdict", "prefer A"],
    ],
  },
  {
    num: "009",
    short: "PROBE",
    code: "ambiguity_probing",
    label: "Probing",
    ms: "440 ms",
    status: "DONE",
    summary:
      "When two candidates disagree, GenQL runs a bounded sample to see whether the disagreement is real. It was: 6 rows against 4.",
    note: "Probing turns an argument between two drafts into a fact, at the cost of one small read.",
    detail: [
      ["probes run", "2"],
      ["row limit", "1000"],
      ["A returns", "6"],
      ["B returns", "4"],
      ["disagreement", "material"],
    ],
  },
  {
    num: "010",
    short: "SELECT",
    code: "candidate_selection",
    label: "Selection",
    ms: "160 ms",
    status: "DONE",
    summary:
      "Ranks what is left on validation, critique severity and probe agreement. A wins, and the reason is recorded rather than implied.",
    note: "Candidate A: 0.91. Candidate B: 0.42 — penalised for the dropped history the critique found.",
    detail: [
      ["winner", "candidate A"],
      ["score", "0.91"],
      ["runner-up", "0.42"],
      ["tiebreak", "critique severity"],
      ["recorded", "yes"],
    ],
  },
  {
    num: "011",
    short: "COST",
    code: "rewrite_and_cost_gate",
    label: "Cost gate",
    ms: "210 ms",
    status: "DONE",
    summary:
      "Rewrites for the target dialect, then estimates the scan. Above your ceiling it waits for a human instead of running.",
    note: "12 KB estimated against a 500 MB ceiling — cleared automatically. The number is shown either way.",
    detail: [
      ["dialect", "Postgres"],
      ["rewrites applied", "1"],
      ["est. scan", "12 KB"],
      ["ceiling", "500 MB"],
      ["gate", "cleared"],
    ],
  },
  {
    num: "012",
    short: "RUN",
    code: "guarded_execution",
    label: "Execution",
    ms: "41 ms",
    status: "DONE",
    summary:
      "Runs under a read-only role with a row cap and a statement timeout. Nothing in this pipeline can write to your warehouse.",
    note: "Read-only by construction, not by policy — the role GenQL connects with has no write grants.",
    detail: [
      ["role", "genql_readonly"],
      ["rows returned", "5"],
      ["row cap", "10 000"],
      ["timeout", "30 s"],
      ["wall time", "41 ms"],
    ],
  },
]
