from __future__ import annotations

from sqlalchemy import Engine

from genql.domain.entities.metric import Metric
from genql.repositories.semantic.metric_repository import PostgresMetricRepository


def test_write_upserts_by_name(migrated_engine: Engine) -> None:
    repo = PostgresMetricRepository(migrated_engine)
    metric = Metric(
        datasource_name="local",
        name="net_sales",
        sql_expression="a - b",
        grain="line_item",
    )

    written = repo.write([metric])
    rewritten = repo.write([Metric(**{**metric.model_dump(), "sql_expression": "a - b - c"})])

    assert written == 1
    assert rewritten == 1
