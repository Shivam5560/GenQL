"""with_overrides is the whole ablation mechanism, so it gets its own test:
the override lands, the base container is untouched, and an unknown field is
refused rather than silently ignored — a typo'd override would produce a
'no delta' result that looks like a finding."""

from __future__ import annotations

import pytest

from genql.composition_root import Container


@pytest.fixture(autouse=True)
def _required_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings.semantic_dsn has no default (deliberately, per genql/core/settings.py),
    # so every bare `Container()` in this module needs it in the environment —
    # the same DSN the `container` fixture in conftest.py uses.
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", "postgresql+psycopg://x:x@localhost/x")


def test_an_override_reaches_settings() -> None:
    container = Container.with_overrides(domain_scoping_enabled=False)

    assert container.settings().domain_scoping_enabled is False


def test_the_base_container_is_unaffected() -> None:
    Container.with_overrides(domain_scoping_enabled=False)

    assert Container().settings().domain_scoping_enabled is True


def test_several_overrides_apply_together() -> None:
    container = Container.with_overrides(probing_enabled=False, cost_budget=1.0)

    assert container.settings().probing_enabled is False
    assert container.settings().cost_budget == 1.0


def test_an_unknown_field_is_refused() -> None:
    with pytest.raises(ValueError, match="not_a_setting"):
        Container.with_overrides(not_a_setting=False)
