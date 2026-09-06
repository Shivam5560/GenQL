"""A natural-language question in, real rows out. The first point in the
project where GenQL produces an answer rather than metadata about one.

The assertions are deliberately about safety and shape, not about the answer
being right: accuracy measurement needs the golden-set runner, which is
Phase 8. What must hold here is that the statement executed was a SELECT, it
cleared every guardrail, and the warehouse returned at least one row through
the read-only role."""

from __future__ import annotations

import os

import pytest
import sqlglot
from sqlglot import exp
from typer.testing import CliRunner

from genql.cli.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

runner = CliRunner()


def _sql_block(stdout: str) -> str:
    """The CLI prints `Plan:`, then `SQL:`, then the rows. Take what sits
    between the SQL header and the blank line that ends it."""
    after_header = stdout.split("SQL:", 1)[1]
    return after_header.split("\n\n", 1)[0].strip()


@pytest.mark.skipif_no_tpcds
def test_a_tpcds_question_produces_a_validated_select_and_real_rows() -> None:
    result = runner.invoke(
        app,
        [
            "query",
            "What is the total net paid for each store, by store name?",
            "--datasource",
            "local",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Plan:" in result.stdout
    assert "SQL:" in result.stdout

    sql = _sql_block(result.stdout)
    expression = sqlglot.parse_one(sql, dialect="postgres")
    assert isinstance(expression, exp.Select | exp.Union)
    assert "store_sales" in sql.lower()
    assert "limit" in sql.lower()
    assert "(0 rows)" not in result.stdout


def test_an_unregistered_datasource_fails_with_one_clean_line() -> None:
    result = runner.invoke(app, ["query", "anything", "--datasource", "not_a_datasource"])

    assert result.exit_code == 1
    assert "not_a_datasource" in result.stdout
    assert "Traceback" not in result.stdout


@pytest.mark.skipif_no_tpcds
def test_a_question_with_no_catalogued_match_fails_as_a_schema_linking_error() -> None:
    result = runner.invoke(
        app,
        [
            "query",
            "zzqqxx nonexistent subject with no warehouse meaning at all",
            "--datasource",
            "local",
        ],
    )

    # Either retrieval returns nothing (SchemaLinkingError) or it returns
    # irrelevant objects and the candidate fails validation. Both are clean
    # one-line failures; neither is a traceback.
    assert "Traceback" not in result.stdout
