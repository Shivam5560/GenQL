"""Order-insensitive execution-result comparison.

The parent spec's §15: results are compared, never SQL strings. Three
normalizations make that comparison mean what it should:

Columns are matched by lower-cased name and the generated result's columns are
permuted into the reference's order, because a generated statement may
legitimately project in a different order and that is not a wrong answer.

Rows are compared as multisets. Not lists, because ORDER BY is not part of
most questions; not sets, because a query that returns three identical rows is
genuinely different from one that returns one, and collapsing them would hide
exactly the GROUP BY bug this comparison exists to catch.

Numbers are normalized to float within a fixed relative precision, because a
warehouse returns Decimal while a rewritten aggregate may return float for the
same value. `None` is never normalized to anything: NULL and 0 are different
answers.
"""

from __future__ import annotations

import math
from collections import Counter
from decimal import Decimal
from typing import Any

from genql.domain.entities.execution_result import ExecutionResult


def _key(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal | int | float):
        # Rounded to a fixed relative precision so that Decimal("10.50"), 10.5,
        # and 10.500000000000001 all land on the same key. Comparing with
        # math.isclose per pair would be O(n^2) over the whole result set.
        as_float = float(value)
        if not math.isfinite(as_float):
            return as_float
        return round(as_float, 9)
    return str(value)


class ResultComparator:
    """Pure, order-insensitive comparison of two `ExecutionResult`s."""

    def compare(
        self, reference: ExecutionResult, generated: ExecutionResult
    ) -> tuple[bool, str | None]:
        reference_columns = [c.lower() for c in reference.columns]
        generated_columns = [c.lower() for c in generated.columns]

        missing = [c for c in reference_columns if c not in generated_columns]
        extra = [c for c in generated_columns if c not in reference_columns]
        if missing or extra:
            return False, (
                f"column mismatch: missing {missing or 'none'}, unexpected {extra or 'none'}"
            )

        order = [generated_columns.index(c) for c in reference_columns]
        reference_rows = Counter(tuple(_key(v) for v in row) for row in reference.rows)
        generated_rows = Counter(tuple(_key(row[i]) for i in order) for row in generated.rows)
        if reference_rows == generated_rows:
            return True, None
        return False, (
            f"result mismatch: reference returned {len(reference.rows)} rows, "
            f"generated returned {len(generated.rows)}"
        )
