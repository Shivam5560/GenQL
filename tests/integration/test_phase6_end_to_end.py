"""The phase's acceptance evidence, driven through the real CLI.

Everything below needs a live model, a seeded tpcds schema, and a migrated
database. Gated and skipped cleanly without them, exactly as Phase 5's
end-to-end file is.

The pause/resume test is the only one that proves the phase actually works.
The others exist so that a failure has somewhere to point: if the well-specified
question also pauses, the gate is over-firing; if the non-SQL question reaches
schema linking, the intent edge is wrong; if the resumed turn re-asks the same
question, the clarifications are not surviving the checkpoint.
"""

from __future__ import annotations

import os
import re

import pytest
from sqlalchemy import Engine
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("GENQL_OPENROUTER_API_KEY"),
        reason="GENQL_OPENROUTER_API_KEY not set",
    ),
    pytest.mark.skipif_no_tpcds,
]

runner = CliRunner()
THREAD_LINE = re.compile(r"^thread: (t-[0-9a-f]+)$", re.MULTILINE)


@pytest.fixture(autouse=True)
def _fresh_container(migrated_engine: Engine) -> None:
    """Singletons carry a connection pool; reset so each test builds its own."""
    Container().reset_singletons()


def test_a_well_specified_question_answers_in_one_invocation() -> None:
    result = runner.invoke(app, ["query", "how many stores do we have", "--datasource", "local"])

    assert result.exit_code == 0, result.stdout
    assert "SQL:" in result.stdout
    assert "select" in result.stdout.lower()
    # No pause: a fully specified counting question must not cost a round trip.
    assert "Answer with:" not in result.stdout
    assert "rows)" in result.stdout


def test_an_under_specified_question_pauses_and_then_resumes_to_real_rows() -> None:
    """The whole phase, end to end."""
    paused = runner.invoke(app, ["query", "show me store sales", "--datasource", "local"])

    assert paused.exit_code == 0, paused.stdout
    assert "Answer with:" in paused.stdout
    match = THREAD_LINE.search(paused.stdout)
    assert match is not None, paused.stdout
    thread_id = match.group(1)

    resumed = runner.invoke(
        app,
        [
            "query",
            "net paid, by store name, for calendar year 2001",
            "--datasource",
            "local",
            "--thread-id",
            thread_id,
        ],
    )

    assert resumed.exit_code == 0, resumed.stdout
    assert "SQL:" in resumed.stdout
    assert "select" in resumed.stdout.lower()
    assert "rows)" in resumed.stdout


def test_a_non_analytical_question_short_circuits_without_generating_sql() -> None:
    result = runner.invoke(app, ["query", "hello, who are you", "--datasource", "local"])

    assert result.exit_code == 0, result.stdout
    assert "SQL:" not in result.stdout
    assert "analytical" in result.stdout.lower()


def test_the_yaml_rules_are_reported_as_applied_defaults() -> None:
    """genql_rule reaching the answer, proving the whole overlay path: YAML →
    PostgresRuleWriter → genql_rule → PostgresRuleReader → the gate → the CLI."""
    overlay = runner.invoke(app, ["semantic", "overlay", "--datasource", "local"])
    assert overlay.exit_code == 0, overlay.stdout
    assert "rules" in overlay.stdout

    result = runner.invoke(app, ["query", "how many stores do we have", "--datasource", "local"])

    assert "Resolved via rule" in result.stdout
    assert "time_range" in result.stdout


def test_resuming_an_unknown_thread_does_not_crash() -> None:
    """A thread id nobody checkpointed has no pending interrupt to resume.
    resume_query must refuse with a typed error before invoking the graph, not
    let it run from START with an empty state and blow up on a missing key.

    `result.exception is None` is the assertion that actually catches a crash:
    CliRunner puts an uncaught exception there, not in captured stdout, so a
    test that only greps stdout for "Traceback" passes even when the CLI
    crashed underneath the runner's own exception handling.
    """
    result = runner.invoke(
        app,
        ["query", "last quarter", "--datasource", "local", "--thread-id", "t-deadbeef"],
    )

    assert result.exception is None
    assert "Traceback" not in result.stdout
    assert result.exit_code == 1
    assert "t-deadbeef" in result.stdout
