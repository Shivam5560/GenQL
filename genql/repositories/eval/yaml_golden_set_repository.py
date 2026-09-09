"""Reads golden cases from `*.yaml` under one directory.

Every failure is loud. A missing directory, an unreadable file, a case with a
missing field, and a case naming a failure class that does not exist all raise
GoldenSetError naming the file — because the alternative, skipping quietly,
makes an accuracy number optimistic in a way nothing downstream can detect.

Files are read in sorted filename order and cases keep their in-file order, so
two runs over the same directory produce the same sequence. An ablation delta
compares two runs case-for-case; an unstable order would compare different
sets and report the difference as an effect.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from genql.domain.entities.golden_case import GoldenCase
from genql.domain.errors import GoldenSetError


class YamlGoldenSetReader:
    def __init__(self, directory: str) -> None:
        self._directory = Path(directory)

    def read_cases(self, datasource_name: str | None = None) -> tuple[GoldenCase, ...]:
        if not self._directory.is_dir():
            raise GoldenSetError(f"no golden-set directory at {self._directory}")

        cases: list[GoldenCase] = []
        for path in sorted(self._directory.glob("*.yaml")):
            cases.extend(self._read_file(path))

        if datasource_name is None:
            return tuple(cases)
        return tuple(c for c in cases if c.datasource_name == datasource_name)

    @staticmethod
    def _read_file(path: Path) -> list[GoldenCase]:
        try:
            payload = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            raise GoldenSetError(f"{path.name}: could not be read: {exc}") from exc

        raw_cases = (payload or {}).get("cases")
        if not isinstance(raw_cases, list):
            raise GoldenSetError(f"{path.name}: expected a top-level `cases` list")

        parsed: list[GoldenCase] = []
        for index, raw in enumerate(raw_cases):
            try:
                parsed.append(GoldenCase.model_validate(raw))
            except ValidationError as exc:
                raise GoldenSetError(f"{path.name}: case {index} is invalid: {exc}") from exc
        return parsed
