"""File I/O, so an integration test even though no database is involved.

The malformed-file assertion matters more than the happy path: a reader that
silently skips a broken fixture makes every accuracy number afterwards quietly
optimistic, and nothing downstream can detect it."""

from __future__ import annotations

from pathlib import Path

import pytest

from genql.domain.errors import GoldenSetError
from genql.repositories.eval.yaml_golden_set_repository import YamlGoldenSetReader

VALID = """
cases:
  - case_id: c1
    question: how many customers
    datasource_name: local
    failure_class: ambiguous_intent
    reference_sql: SELECT count(*) FROM tpcds.customer
  - case_id: c2
    question: how many stores
    datasource_name: other
    failure_class: context_sensitivity
    reference_sql: SELECT count(*) FROM tpcds.store
"""


def test_every_case_in_every_file_is_read(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(VALID)

    cases = YamlGoldenSetReader(str(tmp_path)).read_cases()

    assert {c.case_id for c in cases} == {"c1", "c2"}


def test_cases_can_be_filtered_by_datasource(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(VALID)

    cases = YamlGoldenSetReader(str(tmp_path)).read_cases("local")

    assert [c.case_id for c in cases] == ["c1"]


def test_cases_are_returned_in_a_stable_order(tmp_path: Path) -> None:
    """Two runs of the same fixtures must line up case-for-case, or an
    ablation delta is comparing different sets."""
    (tmp_path / "b.yaml").write_text(VALID)
    (tmp_path / "a.yaml").write_text(VALID.replace("c1", "a1").replace("c2", "a2"))

    first = [c.case_id for c in YamlGoldenSetReader(str(tmp_path)).read_cases()]
    second = [c.case_id for c in YamlGoldenSetReader(str(tmp_path)).read_cases()]

    assert first == second == sorted(first)


def test_a_malformed_file_raises_and_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("cases:\n  - case_id: c1\n    question: q\n")

    with pytest.raises(GoldenSetError) as exc:
        YamlGoldenSetReader(str(tmp_path)).read_cases()

    assert "broken.yaml" in str(exc.value)


def test_an_unknown_failure_class_raises(tmp_path: Path) -> None:
    (tmp_path / "bad_class.yaml").write_text(VALID.replace("ambiguous_intent", "invented"))

    with pytest.raises(GoldenSetError):
        YamlGoldenSetReader(str(tmp_path)).read_cases()


def test_a_missing_directory_raises_rather_than_returning_nothing(tmp_path: Path) -> None:
    with pytest.raises(GoldenSetError):
        YamlGoldenSetReader(str(tmp_path / "nope")).read_cases()


def test_the_repositorys_own_fixtures_load(tmp_path: Path) -> None:
    """The committed fixtures must parse, or every later task's runs are empty."""
    cases = YamlGoldenSetReader("golden").read_cases()

    assert len(cases) >= 6
