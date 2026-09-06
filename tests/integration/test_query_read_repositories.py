"""The three read sides schema linking needs. All are plain SELECTs against
tables Phases 2.5-4 already created, so the only thing worth asserting is the
shape they hand back and the filtering they apply."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, text

from genql.domain.entities.metric import Metric
from genql.repositories.query.object_name_repository import PostgresObjectNameReader
from genql.repositories.semantic.join_path_reader_repository import PostgresJoinPathReader
from genql.repositories.semantic.metric_repository import PostgresMetricRepository

DS = "query_reads_test"


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_object "
                "(datasource_name, schema_name, object_name, object_type) VALUES "
                "(:ds, 'shop', 'orders', 'table'), (:ds, 'shop', 'customers', 'table') "
                "ON CONFLICT DO NOTHING"
            ),
            {"ds": DS},
        )
        conn.execute(
            text(
                "INSERT INTO genql.genql_join_path "
                "(datasource_name, schema_name, source_object, target_object, path, weight) "
                "VALUES (:ds, 'shop', 'orders', 'customers', ARRAY['orders','customers'], 1.0) "
                "ON CONFLICT ON CONSTRAINT pk_genql_join_path DO NOTHING"
            ),
            {"ds": DS},
        )


def test_object_names_come_back_schema_qualified_and_lowercased(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema(DS, "shop")
    _seed(migrated_engine)

    names = PostgresObjectNameReader(migrated_engine).read_object_names(DS)

    assert "shop.orders" in names
    assert "shop.customers" in names


def test_join_paths_are_filtered_to_the_objects_asked_for(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema(DS, "shop")
    _seed(migrated_engine)
    reader = PostgresJoinPathReader(migrated_engine)

    matched = reader.read_join_paths(DS, ["orders"])
    unmatched = reader.read_join_paths(DS, ["nothing_here"])

    assert [p.target_object for p in matched] == ["customers"]
    assert list(unmatched) == []


def test_an_empty_object_name_list_reads_nothing(migrated_engine: Engine) -> None:
    assert list(PostgresJoinPathReader(migrated_engine).read_join_paths(DS, [])) == []


def test_metrics_round_trip_through_the_same_repository(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema(DS, "shop")
    repository = PostgresMetricRepository(migrated_engine)
    repository.write(
        [Metric(datasource_name=DS, name="net_revenue", sql_expression="sum(o.total)", grain="day")]
    )

    metrics = repository.read_metrics(DS)

    assert [m.name for m in metrics] == ["net_revenue"]
    assert metrics[0].sql_expression == "sum(o.total)"
