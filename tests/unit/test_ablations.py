"""Each ablation's identity, and the two properties the harness depends on:
`full` changes nothing, and exactly one ablation needs a recompile. A second
recompiling ablation appearing without anyone noticing would double every
ablation run's cost silently."""

from __future__ import annotations

import pytest

from genql.core.settings import Settings
from genql.domain.ports.ambiguity_example_reader import AmbiguityExampleReader
from genql.domain.ports.join_path_reader import JoinPathReader
from genql.repositories.null.null_ambiguity_example_reader import NullAmbiguityExampleReader
from genql.repositories.null.null_join_path_reader import NullJoinPathReader
from genql.services.eval.ablations import ABLATIONS


def test_the_registry_holds_the_six_ablations() -> None:
    assert ABLATIONS.keys() == [
        "full",
        "no_ambiguity_examples",
        "no_descriptions",
        "no_domains",
        "no_join_paths",
        "no_probing",
    ]


def test_every_ablation_reports_its_own_registry_key_as_its_name() -> None:
    for key in ABLATIONS.keys():  # noqa: SIM118 - Registry, not a dict
        assert ABLATIONS.create(key).name == key


def test_the_baseline_overrides_nothing_and_needs_no_recompile() -> None:
    full = ABLATIONS.create("full")

    assert full.setting_overrides == ()
    assert full.requires_recompile is False


def test_only_no_descriptions_requires_a_recompile() -> None:
    recompiling = [
        k
        for k in ABLATIONS.keys()  # noqa: SIM118 - Registry, not a dict
        if ABLATIONS.create(k).requires_recompile
    ]

    assert recompiling == ["no_descriptions"]


@pytest.mark.parametrize(
    ("key", "field"),
    [
        ("no_descriptions", "enrichment_enabled"),
        ("no_domains", "domain_scoping_enabled"),
        ("no_join_paths", "join_paths_enabled"),
        ("no_probing", "probing_enabled"),
        ("no_ambiguity_examples", "ambiguity_examples_enabled"),
    ],
)
def test_each_ablation_switches_off_exactly_its_own_layer(key: str, field: str) -> None:
    ablation = ABLATIONS.create(key)

    assert ablation.setting_overrides == ((field, False),)


def test_every_overridden_field_actually_exists_on_settings() -> None:
    """The override is applied by name, so a typo would be a silent no-op —
    the ablation would report 'no delta' because nothing was switched off."""
    for key in ABLATIONS.keys():  # noqa: SIM118 - Registry, not a dict
        for field, _ in ABLATIONS.create(key).setting_overrides:
            assert field in Settings.model_fields


def test_every_ablation_carries_a_description_for_the_report_header() -> None:
    for key in ABLATIONS.keys():  # noqa: SIM118 - Registry, not a dict
        assert ABLATIONS.create(key).description


def test_null_join_path_reader_satisfies_its_port() -> None:
    assert isinstance(NullJoinPathReader(), JoinPathReader)


def test_null_ambiguity_example_reader_satisfies_its_port() -> None:
    assert isinstance(NullAmbiguityExampleReader(), AmbiguityExampleReader)
