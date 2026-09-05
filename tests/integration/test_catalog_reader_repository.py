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
