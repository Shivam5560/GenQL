"""The parent spec's §17: "each rewrite rule preserves results on the golden
set", scaled to what this phase can build.

One rule at a time, in isolation, rather than the whole pipeline: a pipeline
test tells you the output changed, a per-rule test tells you which rule broke
it. The comparison is order-insensitive because a rewrite may legitimately
change row order — which is exactly why §15 forbids comparing SQL strings and
requires comparing result sets.

The pre-rewrite SQL is rendered *before* the rule runs. sqlglot's passes mutate
the tree in place and hand back the same instance, so rendering the expression
afterwards would render the rewritten statement under both names and the
assertion would compare a result set against itself.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import sqlglot
import yaml
from sqlglot.optimizer.qualify import qualify

from genql.domain.entities.execution_result import ExecutionResult
from genql.repositories.query.query_executor_repository import ReadOnlyQueryExecutorRepository
from genql.repositories.query.rewrite_rules import REWRITE_RULES

pytestmark = [pytest.mark.integration, pytest.mark.skipif_no_tpcds]

CASES = yaml.safe_load(Path("golden/phase7_equivalence.yaml").read_text())["cases"]

_ROW_CAP = 10_000


def _multiset(result: ExecutionResult) -> Counter[tuple[Any, ...]]:
    return Counter(tuple(row) for row in result.rows)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case_id"])
@pytest.mark.parametrize("rule_key", REWRITE_RULES.keys())
def test_each_rule_preserves_the_result_set(
    case: dict[str, Any],
    rule_key: str,
    warehouse_executor: ReadOnlyQueryExecutorRepository,
    tpcds_schema: dict[str, object],
) -> None:
    expression = qualify(
        sqlglot.parse_one(case["reference_sql"], dialect="postgres"),
        dialect="postgres",
        schema=tpcds_schema,
        identify=False,
    )
    original = expression.sql(dialect="postgres")
    rewritten = REWRITE_RULES.create(rule_key).apply(expression).sql(dialect="postgres")

    before = warehouse_executor.execute(original, _ROW_CAP)
    after = warehouse_executor.execute(rewritten, _ROW_CAP)

    assert _multiset(before) == _multiset(after), (
        f"{rule_key} changed the result of {case['case_id']}\n"
        f"before: {original}\nafter:  {rewritten}"
    )
