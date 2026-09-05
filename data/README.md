# Warehouse seeds

| Seed | Command | Purpose |
|---|---|---|
| TPC-DS SF1 | `uv run python data/seed_tpcds.py --scale 1` | Primary warehouse. 24 tables, cryptic column names, real fiscal date dimension, 99 query templates for later behavioural enrichment. |
| Pagila | `./data/seed_pagila.sh` | Small clean fixture for a fast test loop. |

Olist (messy real-world data, some Portuguese column names) is added in Phase 4
when ambiguity handling is built.
