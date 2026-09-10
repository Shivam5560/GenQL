"""The rule that would have caught the DatetimeFieldOverflow in production.

The statement in `FAILING_STATEMENT` is the one a live turn actually produced
and the warehouse actually rejected, pasted verbatim: it is the regression this
whole rule exists for, and paraphrasing it would let a variation of the same
bug pass.
"""

from __future__ import annotations

from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.surrogate_key_date_guardrail import SurrogateKeyDateGuardrail

FAILING_STATEMENT = """
WITH date_bounds AS (
  SELECT TO_DATE(CAST(MAX(store_sales.ss_sold_date_sk) AS TEXT), 'YYYYMMDD')
         - INTERVAL '12 MONTHS' AS cutoff_date
  FROM tpcds.store_sales AS store_sales
)
SELECT s.s_store_id, SUM(ss.ss_ext_sales_price) AS total_sales
FROM tpcds.store_sales AS ss
JOIN tpcds.store AS s ON s.s_store_sk = ss.ss_store_sk
JOIN date_bounds AS b
  ON b.cutoff_date <= TO_DATE(CAST(ss.ss_sold_date_sk AS TEXT), 'YYYYMMDD')
GROUP BY s.s_store_id
ORDER BY total_sales DESC
LIMIT 10
"""

CORRECT_STATEMENT = """
SELECT s.s_store_id, SUM(ss.ss_ext_sales_price) AS total_sales
FROM tpcds.store_sales AS ss
JOIN tpcds.store AS s ON s.s_store_sk = ss.ss_store_sk
JOIN tpcds.date_dim AS d ON d.d_date_sk = ss.ss_sold_date_sk
WHERE d.d_date >= DATE '2001-01-01'
GROUP BY s.s_store_id
ORDER BY total_sales DESC
LIMIT 10
"""

OBJECTS = frozenset({"tpcds.store_sales", "tpcds.store", "tpcds.date_dim"})


def _rule(objects: frozenset[str] = OBJECTS) -> SurrogateKeyDateGuardrail:
    return SurrogateKeyDateGuardrail(
        GuardrailConfig(row_cap=1000, statement_timeout_ms=30_000, allowed_objects=objects)
    )


def test_the_statement_the_warehouse_rejected_is_rejected_here_first() -> None:
    violations = _rule().check(FAILING_STATEMENT)

    assert len(violations) == 1
    assert "ss_sold_date_sk" in violations[0].message


def test_the_message_names_the_join_that_fixes_it() -> None:
    """A violation the generator cannot act on costs a retry and produces the
    same statement again."""
    message = _rule().check(FAILING_STATEMENT)[0].message

    assert "tpcds.date_dim" in message


def test_the_message_stays_actionable_when_no_date_dimension_is_catalogued() -> None:
    message = _rule(frozenset({"tpcds.store_sales"})).check(FAILING_STATEMENT)[0].message

    assert "dimension table" in message


def test_the_violation_is_not_repairable_so_the_turn_regenerates() -> None:
    assert all(not v.repairable for v in _rule().check(FAILING_STATEMENT))


def test_the_correct_join_passes() -> None:
    assert _rule().check(CORRECT_STATEMENT) == ()


def test_every_way_of_reading_a_surrogate_key_as_a_date_is_caught() -> None:
    """One rule, not five: each of these is the same mistake spelled
    differently, and catching four of the five is not catching the mistake."""
    for sql in (
        "SELECT CAST(ss_sold_date_sk AS DATE) FROM tpcds.store_sales",
        "SELECT ss_sold_date_sk::date FROM tpcds.store_sales",
        "SELECT TO_TIMESTAMP(ss_sold_date_sk) FROM tpcds.store_sales",
        "SELECT TO_CHAR(ss_sold_date_sk, 'YYYY') FROM tpcds.store_sales",
        "SELECT ss_sold_date_sk - INTERVAL '12 months' FROM tpcds.store_sales",
        "SELECT EXTRACT(YEAR FROM ss_sold_date_sk) FROM tpcds.store_sales",
        "SELECT MAKE_DATE(ss_sold_date_sk, 1, 1) FROM tpcds.store_sales",
        "SELECT DATE_TRUNC('month', TO_DATE(ss_sold_date_sk::text, 'YYYYMMDD')) "
        "FROM tpcds.store_sales",
    ):
        assert _rule().check(sql) != (), sql


def test_a_surrogate_key_used_as_a_key_is_left_alone() -> None:
    """The rule is about reading the key as a time, not about mentioning it —
    a join, a group by, and a count over one are all correct."""
    for sql in (
        "SELECT COUNT(*) FROM tpcds.store_sales GROUP BY ss_sold_date_sk",
        "SELECT MAX(ss_sold_date_sk) FROM tpcds.store_sales",
        "SELECT CAST(ss_sold_date_sk AS TEXT) FROM tpcds.store_sales",
        "SELECT * FROM tpcds.store_sales WHERE ss_sold_date_sk = 2452642",
    ):
        assert _rule().check(sql) == (), sql


def test_real_date_columns_may_still_be_treated_as_dates() -> None:
    sql = (
        "SELECT DATE_TRUNC('month', d.d_date) FROM tpcds.date_dim AS d "
        "WHERE d.d_date > CURRENT_DATE - INTERVAL '12 months'"
    )

    assert _rule().check(sql) == ()


def test_an_unparseable_statement_is_left_to_statement_kind() -> None:
    """Two rules reporting the same parse failure gives the generator two
    contradictory things to fix."""
    assert _rule().check("SELECT FROM WHERE ((") == ()
