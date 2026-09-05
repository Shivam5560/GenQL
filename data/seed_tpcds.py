"""Generate TPC-DS at a given scale factor and load it into Postgres.

TPC-DS is chosen because its column names are deliberately cryptic
(ss_ext_sales_price, d_moy, cd_demo_sk), which gives schema discovery real work.

DuckDB's dsdgen emits zero constraints, so after loading we add TPC-DS's
documented primary and foreign keys (every dimension's surrogate key as its
primary key, every fact/returns/inventory *_sk column as a foreign key to its
dimension) and ANALYZE every table. Both steps are guarded so a re-run is
idempotent.
"""

from __future__ import annotations

import argparse
import pathlib
import tempfile

import duckdb
from sqlalchemy import Engine, text

from genql.core.settings import Settings
from genql.infrastructure.db.engine import create_engine_from_dsn

# Each dimension table's TPC-DS primary key (its surrogate key column).
_DIMENSION_PRIMARY_KEYS: dict[str, str] = {
    "date_dim": "d_date_sk",
    "time_dim": "t_time_sk",
    "item": "i_item_sk",
    "customer": "c_customer_sk",
    "customer_demographics": "cd_demo_sk",
    "household_demographics": "hd_demo_sk",
    "customer_address": "ca_address_sk",
    "store": "s_store_sk",
    "promotion": "p_promo_sk",
    "reason": "r_reason_sk",
    "call_center": "cc_call_center_sk",
    "catalog_page": "cp_catalog_page_sk",
    "ship_mode": "sm_ship_mode_sk",
    "warehouse": "w_warehouse_sk",
    "web_page": "wp_web_page_sk",
    "web_site": "web_site_sk",
}

# Every fact/returns/inventory *_sk column and the dimension it references.
_FOREIGN_KEYS: dict[str, list[tuple[str, str]]] = {
    "store_sales": [
        ("ss_sold_date_sk", "date_dim"),
        ("ss_sold_time_sk", "time_dim"),
        ("ss_item_sk", "item"),
        ("ss_customer_sk", "customer"),
        ("ss_cdemo_sk", "customer_demographics"),
        ("ss_hdemo_sk", "household_demographics"),
        ("ss_addr_sk", "customer_address"),
        ("ss_store_sk", "store"),
        ("ss_promo_sk", "promotion"),
    ],
    "store_returns": [
        ("sr_returned_date_sk", "date_dim"),
        ("sr_return_time_sk", "time_dim"),
        ("sr_item_sk", "item"),
        ("sr_customer_sk", "customer"),
        ("sr_cdemo_sk", "customer_demographics"),
        ("sr_hdemo_sk", "household_demographics"),
        ("sr_addr_sk", "customer_address"),
        ("sr_store_sk", "store"),
        ("sr_reason_sk", "reason"),
    ],
    "catalog_sales": [
        ("cs_sold_date_sk", "date_dim"),
        ("cs_sold_time_sk", "time_dim"),
        ("cs_ship_date_sk", "date_dim"),
        ("cs_bill_customer_sk", "customer"),
        ("cs_bill_cdemo_sk", "customer_demographics"),
        ("cs_bill_hdemo_sk", "household_demographics"),
        ("cs_bill_addr_sk", "customer_address"),
        ("cs_ship_customer_sk", "customer"),
        ("cs_ship_cdemo_sk", "customer_demographics"),
        ("cs_ship_hdemo_sk", "household_demographics"),
        ("cs_ship_addr_sk", "customer_address"),
        ("cs_call_center_sk", "call_center"),
        ("cs_catalog_page_sk", "catalog_page"),
        ("cs_ship_mode_sk", "ship_mode"),
        ("cs_warehouse_sk", "warehouse"),
        ("cs_item_sk", "item"),
        ("cs_promo_sk", "promotion"),
    ],
    "catalog_returns": [
        ("cr_returned_date_sk", "date_dim"),
        ("cr_returned_time_sk", "time_dim"),
        ("cr_item_sk", "item"),
        ("cr_refunded_customer_sk", "customer"),
        ("cr_refunded_cdemo_sk", "customer_demographics"),
        ("cr_refunded_hdemo_sk", "household_demographics"),
        ("cr_refunded_addr_sk", "customer_address"),
        ("cr_returning_customer_sk", "customer"),
        ("cr_returning_cdemo_sk", "customer_demographics"),
        ("cr_returning_hdemo_sk", "household_demographics"),
        ("cr_returning_addr_sk", "customer_address"),
        ("cr_call_center_sk", "call_center"),
        ("cr_catalog_page_sk", "catalog_page"),
        ("cr_ship_mode_sk", "ship_mode"),
        ("cr_warehouse_sk", "warehouse"),
        ("cr_reason_sk", "reason"),
    ],
    "web_sales": [
        ("ws_sold_date_sk", "date_dim"),
        ("ws_sold_time_sk", "time_dim"),
        ("ws_ship_date_sk", "date_dim"),
        ("ws_item_sk", "item"),
        ("ws_bill_customer_sk", "customer"),
        ("ws_bill_cdemo_sk", "customer_demographics"),
        ("ws_bill_hdemo_sk", "household_demographics"),
        ("ws_bill_addr_sk", "customer_address"),
        ("ws_ship_customer_sk", "customer"),
        ("ws_ship_cdemo_sk", "customer_demographics"),
        ("ws_ship_hdemo_sk", "household_demographics"),
        ("ws_ship_addr_sk", "customer_address"),
        ("ws_web_page_sk", "web_page"),
        ("ws_web_site_sk", "web_site"),
        ("ws_ship_mode_sk", "ship_mode"),
        ("ws_warehouse_sk", "warehouse"),
        ("ws_promo_sk", "promotion"),
    ],
    "web_returns": [
        ("wr_returned_date_sk", "date_dim"),
        ("wr_returned_time_sk", "time_dim"),
        ("wr_item_sk", "item"),
        ("wr_refunded_customer_sk", "customer"),
        ("wr_refunded_cdemo_sk", "customer_demographics"),
        ("wr_refunded_hdemo_sk", "household_demographics"),
        ("wr_refunded_addr_sk", "customer_address"),
        ("wr_returning_customer_sk", "customer"),
        ("wr_returning_cdemo_sk", "customer_demographics"),
        ("wr_returning_hdemo_sk", "household_demographics"),
        ("wr_returning_addr_sk", "customer_address"),
        ("wr_web_page_sk", "web_page"),
        ("wr_reason_sk", "reason"),
    ],
    "inventory": [
        ("inv_date_sk", "date_dim"),
        ("inv_item_sk", "item"),
        ("inv_warehouse_sk", "warehouse"),
    ],
}

_CONSTRAINT_EXISTS = text("""
    SELECT 1 FROM pg_constraint con
    JOIN pg_class cl ON cl.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = cl.relnamespace
    WHERE n.nspname = :schema AND cl.relname = :table AND con.conname = :name
""")


def _add_constraint_if_missing(
    engine: Engine, schema: str, table: str, name: str, ddl: str
) -> None:
    """Run `ddl` only if a constraint named `name` does not already exist.

    Postgres has no `ADD CONSTRAINT IF NOT EXISTS`, so existence is checked
    explicitly; this is what makes a re-run of this script idempotent.
    """
    with engine.begin() as conn:
        exists = conn.execute(
            _CONSTRAINT_EXISTS, {"schema": schema, "table": table, "name": name}
        ).first()
        if exists is None:
            conn.execute(text(ddl))


def _add_tpcds_constraints(engine: Engine, schema: str) -> None:
    for table, pk_column in _DIMENSION_PRIMARY_KEYS.items():
        name = f"pk_{table}"
        ddl = f'ALTER TABLE "{schema}"."{table}" ADD CONSTRAINT {name} PRIMARY KEY ("{pk_column}")'
        _add_constraint_if_missing(engine, schema, table, name, ddl)

    for table, foreign_keys in _FOREIGN_KEYS.items():
        for column, ref_table in foreign_keys:
            name = f"fk_{table}_{column}"
            ref_column = _DIMENSION_PRIMARY_KEYS[ref_table]
            ddl = (
                f'ALTER TABLE "{schema}"."{table}" ADD CONSTRAINT {name} '
                f'FOREIGN KEY ("{column}") REFERENCES "{schema}"."{ref_table}" ("{ref_column}")'
            )
            _add_constraint_if_missing(engine, schema, table, name, ddl)


def _analyze_all(engine: Engine, schema: str, tables: list[str]) -> None:
    # ANALYZE cannot run inside the same transaction as the constraint DDL
    # above (server-side default is autocommit-per-statement here anyway),
    # and re-running it is always safe — it just refreshes reltuples/stats.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for table in tables:
            conn.execute(text(f'ANALYZE "{schema}"."{table}"'))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--schema", default="tpcds")
    args = parser.parse_args()

    con = duckdb.connect()
    con.execute("INSTALL tpcds; LOAD tpcds;")
    con.execute(f"CALL dsdgen(sf={args.scale})")
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]

    engine = create_engine_from_dsn(Settings().warehouse_dsn)
    with engine.begin() as conn:
        # Re-runnable: wipe and recreate rather than CREATE TABLE-ing into an
        # already-seeded schema, which would fail on "relation already exists".
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{args.schema}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{args.schema}"'))

    with tempfile.TemporaryDirectory() as tmp:
        for table in tables:
            ddl = con.execute(
                "SELECT sql FROM duckdb_tables() WHERE table_name = ?", [table]
            ).fetchone()[0]
            csv_path = pathlib.Path(tmp) / f"{table}.csv"
            con.execute(f"COPY {table} TO '{csv_path}' (HEADER, DELIMITER ',')")
            with engine.begin() as conn:
                conn.execute(text(f'SET search_path TO "{args.schema}"'))
                conn.execute(text(ddl))
                raw = conn.connection.driver_connection
                with (
                    raw.cursor() as cur,
                    csv_path.open() as fh,
                    cur.copy(
                        f'COPY "{args.schema}"."{table}" FROM STDIN WITH (FORMAT csv, HEADER)'
                    ) as copy,
                ):
                    for line in fh:
                        copy.write(line)
            print(f"loaded {table}")

    print("adding TPC-DS primary and foreign keys")
    _add_tpcds_constraints(engine, args.schema)

    print("analyzing tables")
    _analyze_all(engine, args.schema, tables)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
