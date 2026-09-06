# Warehouse seeds

| Seed | Database | Command | Purpose |
|---|---|---|---|
| TPC-DS SF1 | `genql` | `uv run python data/seed_tpcds.py --scale 1` | Primary warehouse, verified end to end. 24 tables, cryptic column names, real fiscal date dimension, TPC-DS's documented primary/foreign keys added and ANALYZEd after load, 99 query templates for later behavioural enrichment. |
| Pagila | `genql_wh2` | see below | Second **database**, so multi-datasource discovery is demonstrated rather than assumed. Verified: `SELECT count(*) FROM pagila.film` returns 1000. |

Pagila is loaded through `GENQL_SEED_EXEC`, any command that reads SQL on
stdin. There is no local `psql` on the development machine, so it runs inside
the container on the VM:

```bash
ssh genql-vm "docker exec genql-paradedb psql -U genql -d genql -c 'CREATE DATABASE genql_wh2'"
GENQL_SEED_EXEC='ssh genql-vm docker exec -i genql-paradedb psql -U genql -d genql_wh2 -v ON_ERROR_STOP=1' \
  ./data/seed_pagila.sh
```

## Registering them

```bash
uv run genql datasource add --name local --dialect postgres --dsn-env GENQL_WAREHOUSE_DSN
uv run genql datasource add --name wh2   --dialect postgres --dsn-env GENQL_WH2_DSN
uv run genql schema add --datasource local --schema tpcds
uv run genql schema add --datasource wh2   --schema pagila
uv run genql discover --datasource local
```

Olist (messy real-world data, some Portuguese column names) is added in Phase 4
when ambiguity handling is built.
