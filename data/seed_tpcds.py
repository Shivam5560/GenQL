"""Generate TPC-DS at a given scale factor and load it into Postgres.

TPC-DS is chosen because its column names are deliberately cryptic
(ss_ext_sales_price, d_moy, cd_demo_sk), which gives schema discovery real work.
"""

from __future__ import annotations

import argparse
import pathlib
import tempfile

import duckdb
from sqlalchemy import text

from genql.core.settings import Settings
from genql.infrastructure.db.engine import create_engine_from_dsn


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
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{args.schema}"'))

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
                with raw.cursor() as cur, csv_path.open() as fh:
                    with cur.copy(
                        f'COPY "{args.schema}"."{table}" FROM STDIN WITH (FORMAT csv, HEADER)'
                    ) as copy:
                        for line in fh:
                            copy.write(line)
            print(f"loaded {table}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
