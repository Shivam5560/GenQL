# Warehouse seeds

| Seed | Command | Purpose |
|---|---|---|
| TPC-DS SF1 | `uv run python data/seed_tpcds.py --scale 1` | Primary warehouse, verified end to end. 24 tables, cryptic column names, real fiscal date dimension, TPC-DS's documented primary/foreign keys added and ANALYZEd after load, 99 query templates for later behavioural enrichment. |
| Pagila (UNVERIFIED) | `./data/seed_pagila.sh` | Small clean fixture for a fast test loop. Written but never executed in this environment (no local psql client) — believed correct by construction, not proven. Do not treat it as an available fixture until someone runs it and confirms `SELECT count(*) FROM pagila.film`. |

Olist (messy real-world data, some Portuguese column names) is added in Phase 4
when ambiguity handling is built.
