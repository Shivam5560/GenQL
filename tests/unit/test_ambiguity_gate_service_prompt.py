"""AmbiguityGateService's prompt construction and response model, split out
of test_ambiguity_gate_service.py to stay under the house file-length limit:
rules are read for the right datasource, the prompt names only open
dimensions plus prior answers, the builder is pure, and the response model
is frozen."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.services.query.ambiguity_gate_service import (
    AmbiguityGateService,
    GateResponse,
    build_gate_prompt,
)
from tests.unit.test_ambiguity_gate_service import FakeChat, FakeRules, rule, service


def test_rules_are_read_for_the_datasource_the_turn_names() -> None:
    rules = FakeRules(())
    AmbiguityGateService(FakeChat(), rules, 0.7).assess("q", "warehouse_two")  # type: ignore[arg-type]

    assert rules.datasources == ["warehouse_two"]


def test_the_prompt_lists_only_the_open_dimensions_and_the_answers_so_far() -> None:
    chat = FakeChat(vague=("grain",))

    service(chat, rules=(rule("default_period", "time_range"),)).assess(
        "show me revenue", "local", answers=(("entity", "stores"),)
    )

    prompt = chat.prompts[0]
    assert "show me revenue" in prompt
    assert "grain" in prompt
    assert "time_range" not in prompt  # covered by a rule
    assert "stores" in prompt  # already answered, so given as context


def test_the_prompt_builder_is_pure() -> None:
    assert build_gate_prompt("q", ("grain",), ()) == build_gate_prompt("q", ("grain",), ())


def test_the_response_model_is_frozen() -> None:
    response = GateResponse(
        scores=(), clarifying_dimension="entity", clarifying_question="Which one?"
    )

    with pytest.raises(ValidationError):
        response.clarifying_question = "other"
