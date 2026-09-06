"""Validated shape of one semantic/<datasource>.yaml file. Object keys in
`objects` are fully-qualified "schema.object" strings — parsing them apart
into a SchemaRef plus an object name is the overlay service's job, not this
model's, which stays a pure structural validator."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ColumnOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str | None = None
    business_alias: str | None = None
    unit: str | None = None


class ObjectOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str | None = None
    business_alias: str | None = None
    columns: dict[str, ColumnOverlay] = Field(default_factory=dict)


class MetricOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    sql_expression: str
    grain: str
    unit: str | None = None
    default_filters: dict[str, str] = Field(default_factory=dict)


class RuleOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    dimension: str
    value: str
    description: str


class JoinHintOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_object: str
    target_object: str
    path: tuple[str, ...]
    weight: float = 1.0


class SemanticOverlay(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource: str
    objects: dict[str, ObjectOverlay] = Field(default_factory=dict)
    metrics: tuple[MetricOverlay, ...] = ()
    rules: tuple[RuleOverlay, ...] = ()
    join_hints: tuple[JoinHintOverlay, ...] = ()
