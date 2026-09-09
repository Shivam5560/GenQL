"""The densest unit in Part B, because every accuracy number the ablation
harness reports rests on it. Order insensitivity is required by §15; column
reordering is required because a generated statement may legitimately select
in a different order; numeric normalization is required because a warehouse
returns Decimal and a rewritten aggregate may return float for the same value.

Duplicate counts must be preserved: comparing as sets rather than multisets
would call a query that returns three identical rows equal to one that returns
one, which is exactly the kind of wrong answer a GROUP BY bug produces."""

from __future__ import annotations

from decimal import Decimal

from genql.domain.entities.execution_result import ExecutionResult
from genql.services.eval.result_comparator import ResultComparator


def _result(columns: tuple[str, ...], rows: tuple[tuple[object, ...], ...]) -> ExecutionResult:
    return ExecutionResult(columns=columns, rows=rows, row_count=len(rows), truncated=False)


COMPARATOR = ResultComparator()


def test_identical_results_match() -> None:
    a = _result(("id", "total"), ((1, 10), (2, 20)))

    assert COMPARATOR.compare(a, a) == (True, None)


def test_row_order_does_not_matter() -> None:
    reference = _result(("id",), ((1,), (2,), (3,)))
    generated = _result(("id",), ((3,), (1,), (2,)))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_column_order_does_not_matter() -> None:
    reference = _result(("id", "total"), ((1, 10),))
    generated = _result(("total", "id"), ((10, 1),))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_column_names_are_compared_case_insensitively() -> None:
    reference = _result(("Id", "Total"), ((1, 10),))
    generated = _result(("id", "total"), ((1, 10),))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_a_missing_column_is_reported_by_name() -> None:
    reference = _result(("id", "total"), ((1, 10),))
    generated = _result(("id",), ((1,),))

    matched, reason = COMPARATOR.compare(reference, generated)

    assert matched is False
    assert reason is not None
    assert "total" in reason


def test_duplicate_rows_are_counted_not_collapsed() -> None:
    reference = _result(("id",), ((1,), (1,), (1,)))
    generated = _result(("id",), ((1,),))

    assert COMPARATOR.compare(reference, generated)[0] is False


def test_a_decimal_equals_the_same_value_as_a_float() -> None:
    reference = _result(("total",), ((Decimal("10.50"),),))
    generated = _result(("total",), ((10.5,),))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_an_int_equals_the_same_value_as_a_decimal() -> None:
    reference = _result(("n",), ((Decimal("3"),),))
    generated = _result(("n",), ((3,),))

    assert COMPARATOR.compare(reference, generated)[0] is True


def test_floats_differing_beyond_tolerance_do_not_match() -> None:
    reference = _result(("total",), ((10.0,),))
    generated = _result(("total",), ((10.5,),))

    assert COMPARATOR.compare(reference, generated)[0] is False


def test_none_matches_none_and_not_zero() -> None:
    assert COMPARATOR.compare(_result(("x",), ((None,),)), _result(("x",), ((None,),)))[0] is True
    assert COMPARATOR.compare(_result(("x",), ((None,),)), _result(("x",), ((0,),)))[0] is False


def test_two_empty_results_with_the_same_columns_match() -> None:
    reference = _result(("id",), ())
    generated = _result(("id",), ())

    assert COMPARATOR.compare(reference, generated) == (True, None)


def test_a_mismatch_reports_the_row_counts() -> None:
    reference = _result(("id",), ((1,), (2,)))
    generated = _result(("id",), ((1,),))

    matched, reason = COMPARATOR.compare(reference, generated)

    assert matched is False
    assert reason is not None
    assert "2" in reason and "1" in reason
