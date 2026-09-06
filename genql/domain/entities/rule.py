"""A YAML-authored default for one ambiguity-gate dimension.

Never LLM-guessed, exactly like Metric: nothing else in the system proposes a
rule, so there is no merge step and no provenance column to reconcile — the
YAML file is the only author, and `genql semantic overlay` simply upserts it.

`dimension` is a plain str, not Literal[*AMBIGUITY_DIMENSIONS]. A typo'd
dimension is silently never applied rather than rejected at write time, which
is the same "fail visibly downstream, not upfront" tradeoff Phase 4 accepted
for Metric.sql_expression. Tightening it is a one-line follow-up once it
proves worth doing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Rule(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    dimension: str
    value: str
    description: str
