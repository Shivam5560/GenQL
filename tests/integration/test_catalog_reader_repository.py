from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.repositories.warehouse.catalog_reader_repository import (
    PostgresCatalogReaderRepository,
)

FIXTURE = """
DROP SCHEMA IF EXISTS shop CASCADE;
CREATE SCHEMA shop;
CREATE TABLE shop.customer (
    c_customer_sk BIGINT PRIMARY KEY,
    c_state       TEXT
);
CREATE TABLE shop.orders (
    o_order_sk    BIGINT PRIMARY KEY,
    o_customer_sk BIGINT NOT NULL REFERENCES shop.customer(c_customer_sk),
    o_amount      NUMERIC(10,2)
);
CREATE VIEW shop.order_summary AS SELECT o_customer_sk, SUM(o_amount) AS total
FROM shop.orders GROUP BY o_customer_sk;
"""


@pytest.fixture(scope="module")
def shop_schema(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(text(FIXTURE))
    return engine


def test_reads_tables_and_views(shop_schema: Engine) -> None:
    repo = PostgresCatalogReaderRepository(shop_schema)
    objects = {o.object_name: o for o in repo.read_objects("shop")}
    assert set(objects) == {"customer", "orders", "order_summary"}
    assert objects["customer"].object_type is ObjectType.TABLE
    assert objects["order_summary"].object_type is ObjectType.VIEW


def test_reads_columns_with_primary_key_flag(shop_schema: Engine) -> None:
    repo = PostgresCatalogReaderRepository(shop_schema)
    columns = {c.qualified_name: c for c in repo.read_columns("shop")}
    pk = columns["shop.customer.c_customer_sk"]
    assert pk.is_primary_key is True
    assert pk.is_nullable is False
    assert pk.ordinal == 1
    assert columns["shop.orders.o_amount"].data_type == "numeric(10,2)"


def test_reads_foreign_key_with_referenced_object(shop_schema: Engine) -> None:
    repo = PostgresCatalogReaderRepository(shop_schema)
    fks = [
        c for c in repo.read_constraints("shop") if c.constraint_type is ConstraintType.FOREIGN_KEY
    ]
    assert len(fks) == 1
    assert fks[0].object_name == "orders"
    assert fks[0].referenced_object_name == "customer"
    assert fks[0].column_names == ("o_customer_sk",)
    assert fks[0].referenced_column_names == ("c_customer_sk",)


def test_primary_key_constraint_has_column_names_but_no_referenced_columns(
    shop_schema: Engine,
) -> None:
    repo = PostgresCatalogReaderRepository(shop_schema)
    pks = [
        c for c in repo.read_constraints("shop") if c.constraint_type is ConstraintType.PRIMARY_KEY
    ]
    customer_pk = next(c for c in pks if c.object_name == "customer")
    assert customer_pk.column_names == ("c_customer_sk",)
    assert customer_pk.referenced_column_names == ()


def test_reltuples_sentinel_is_mapped_to_none_not_zero(engine: Engine) -> None:
    """A never-ANALYZEd table reports reltuples = -1 ('unknown'), not 0 ('empty').

    Clamping -1 to 0 would persist "this table is empty" as a fact even though
    it has 50 rows — see final-review.md finding I1.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS unanalyzed CASCADE"))
        conn.execute(text("CREATE SCHEMA unanalyzed"))
        conn.execute(text("CREATE TABLE unanalyzed.fresh (id INT)"))
        conn.execute(text("INSERT INTO unanalyzed.fresh SELECT generate_series(1, 50)"))

    repo = PostgresCatalogReaderRepository(engine)
    objects = {o.object_name: o for o in repo.read_objects("unanalyzed")}
    assert objects["fresh"].row_estimate is None

    with engine.begin() as conn:
        conn.execute(text("ANALYZE unanalyzed.fresh"))
    analyzed = {o.object_name: o for o in repo.read_objects("unanalyzed")}
    assert analyzed["fresh"].row_estimate == 50
