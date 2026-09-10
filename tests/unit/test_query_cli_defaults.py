"""How `genql query` reports what it decided without being told.

Split out of test_query_cli.py to stay under the house file-length limit,
along a real seam: these are the only tests about the two blocks that answer
"what did this turn assume?" — the rules that fired, and the values applied
for anything the gate ran out of budget to ask about.

Both must be visible or the bargain fails. The gate stops asking after one
question specifically so a turn can proceed on its own reading of the rest;
a reading the user cannot see is one they cannot correct, and the answer is
then silently about a different question than the one they asked.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from genql.cli.main import app
from tests.unit.test_query_cli import _install, finished

runner = CliRunner()


def test_a_finished_turn_reports_the_defaults_it_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A default the user did not ask for must be visible, or the answer is
    silently about a different question than the one they asked."""
    _install(monkeypatch, finished())

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert "time_range" in result.stdout
    assert "default_period" in result.stdout


def test_a_fired_rule_is_named_so_it_can_be_edited(monkeypatch: pytest.MonkeyPatch) -> None:
    """Naming the RULE is what someone who disagrees with a default needs:
    the value alone gives them nothing to go change.

    This replaces a test that asserted the wording said "not yet applied" —
    true when written, since the rule's value reached nothing downstream, and
    false now that PlanningNode states it to the planner as binding.
    """
    _install(monkeypatch, finished())

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert "Applied rules:" in result.stdout
    assert "default_period" in result.stdout
    assert "not yet applied" not in result.stdout


def test_an_assumption_is_shown_with_its_value_and_how_to_change_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An assumption the user cannot see is one they cannot correct, which is
    the whole bargain of assuming instead of asking."""
    response = finished().model_copy(
        update={"assumed": (("time_range", "the most recent complete calendar year"),)}
    )
    _install(monkeypatch, response)

    result = runner.invoke(app, ["query", "how many orders", "--datasource", "local"])

    assert "Assumed without asking" in result.stdout
    assert "the most recent complete calendar year" in result.stdout
