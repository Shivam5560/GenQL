"""Kinds of constraint that carry relationship meaning."""

from __future__ import annotations

from enum import StrEnum


class ConstraintType(StrEnum):
    PRIMARY_KEY = "PRIMARY_KEY"
    FOREIGN_KEY = "FOREIGN_KEY"
    UNIQUE = "UNIQUE"
