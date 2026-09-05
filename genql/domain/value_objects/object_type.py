"""Kinds of database object GenQL discovers."""

from __future__ import annotations

from enum import StrEnum


class ObjectType(StrEnum):
    TABLE = "TABLE"
    VIEW = "VIEW"
    MATERIALIZED_VIEW = "MATERIALIZED_VIEW"
