"""Rejects treating a `_sk` surrogate key as if it were a date.

The failure this exists for: asked for the top stores by sales, the generator
wrote `TO_DATE(CAST(ss_sold_date_sk AS TEXT), 'YYYYMMDD')`. In a star schema
`ss_sold_date_sk` is a foreign key into `date_dim` — TPC-DS numbers those keys
from 2415022 — so the cast produces the string '2452642', which Postgres reads
as the year 245264 and refuses with DatetimeFieldOverflow. The statement is
valid SQL, passes every other guardrail, is costed happily by EXPLAIN, and
dies on execution having spent a full pipeline run.

It is caught statically rather than left to the warehouse because the repair
is a JOIN, not an edit. `repair` therefore raises: rewriting the statement
would mean inventing a join this rule cannot know is correct, and the retry
edge out of static_validation feeds the message below back into candidate
generation, which can.

The rule is about the NAME, not the type. A column called `ss_sold_date_sk`
is an integer in the catalog and so is a column holding 20240115, and no type
information distinguishes them — but the `_sk` suffix is the dimensional
modelling convention that says "this is a row id in another table", and every
schema that uses it uses it consistently. A column genuinely holding a
YYYYMMDD integer is not named `_sk`.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS

_SURROGATE_KEY_SUFFIX = "_sk"

#: Types a cast to which means "I am reading this column as a moment in time".
_TEMPORAL_TYPES = frozenset(
    {
        exp.DataType.Type.DATE,
        exp.DataType.Type.DATE32,
        exp.DataType.Type.DATETIME,
        exp.DataType.Type.DATETIME64,
        exp.DataType.Type.TIME,
        exp.DataType.Type.TIMESTAMP,
        exp.DataType.Type.TIMESTAMPTZ,
        exp.DataType.Type.TIMESTAMPLTZ,
    }
)

#: sqlglot folds each dialect's temporal builtins into these, so matching the
#: classes catches `TO_DATE`, `::date`, `DATE_TRUNC` and `TO_CHAR` without this
#: file carrying a list of Postgres function names that other dialects spell
#: differently.
_TEMPORAL_EXPRESSIONS = (
    exp.StrToDate,
    exp.StrToTime,
    exp.StrToUnix,
    exp.TsOrDsToDate,
    exp.TsOrDsToDatetime,
    exp.TsOrDsAdd,
    exp.TimeToStr,
    exp.TimeToUnix,
    exp.UnixToTime,
    exp.UnixToStr,
    exp.DateTrunc,
    exp.TimestampTrunc,
    exp.DateAdd,
    exp.DateSub,
    exp.DateDiff,
    exp.DatetimeDiff,
    exp.Extract,
    exp.DateFromParts,
    exp.LastDay,
)

#: The ones sqlglot leaves as Anonymous under the postgres dialect.
_TEMPORAL_FUNCTION_NAMES = frozenset({"make_date", "make_timestamp", "age", "to_date"})


def _surrogate_keys(node: exp.Expr) -> list[str]:
    """Every `_sk` column named anywhere beneath `node`, in source order."""
    seen: list[str] = []
    for column in node.find_all(exp.Column):
        name = str(column.name)
        if name.lower().endswith(_SURROGATE_KEY_SUFFIX) and name not in seen:
            seen.append(name)
    return seen


@GUARDRAILS.register("surrogate_key_date")
class SurrogateKeyDateGuardrail:
    name = "surrogate_key_date"
    # After object_allowlist (30), which decides whether the objects exist at
    # all, and before limit_injection (40), whose repair would otherwise
    # rewrite a statement about to be rejected anyway.
    priority = 35

    def __init__(self, config: GuardrailConfig) -> None:
        self._date_dimension = self._find_date_dimension(config.allowed_objects)

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            # statement_kind (priority 10) owns parse failures.
            return ()

        offenders: list[str] = []
        for node in self._temporal_nodes(expression):
            for key in _surrogate_keys(node):
                if key not in offenders:
                    offenders.append(key)
        if not offenders:
            return ()
        return (GuardrailViolation(rule_name=self.name, message=self._message(offenders)),)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))

    @staticmethod
    def _temporal_nodes(expression: exp.Expr) -> list[exp.Expr]:
        nodes: list[exp.Expr] = list(expression.find_all(*_TEMPORAL_EXPRESSIONS))
        nodes += [
            cast
            for cast in expression.find_all(exp.Cast)
            if cast.to is not None and cast.to.this in _TEMPORAL_TYPES
        ]
        nodes += [
            node
            for node in expression.find_all(exp.Anonymous)
            if str(node.this).lower() in _TEMPORAL_FUNCTION_NAMES
        ]
        # `ss_sold_date_sk - INTERVAL '12 months'` names no function and casts
        # nothing, but arithmetic against an INTERVAL is only meaningful on a
        # date — so the operand on the other side of it is being read as one.
        nodes.extend(
            interval.parent
            for interval in expression.find_all(exp.Interval)
            if isinstance(interval.parent, exp.Binary)
        )
        return nodes

    def _message(self, offenders: list[str]) -> str:
        named = ", ".join(offenders)
        plural = "are surrogate keys" if len(offenders) > 1 else "is a surrogate key"
        join_hint = (
            f"Join {self._date_dimension} on it and filter or group by that table's "
            "real date column"
            if self._date_dimension
            else "Join the dimension table it references and filter or group by that "
            "table's real date column"
        )
        return (
            f"{named} {plural} — a row id in a dimension table, not a date and not a "
            "YYYYMMDD number — and this statement reads it as a point in time. Casting "
            "or formatting it as a date yields values the warehouse rejects. "
            f"{join_hint}, rather than converting the key itself."
        )

    @staticmethod
    def _find_date_dimension(allowed_objects: frozenset[str]) -> str | None:
        """The catalogued date dimension, so the message can name it.

        Best effort and deliberately conservative: a schema whose date table is
        called something this does not recognise gets the generic sentence,
        which is still actionable. Naming the wrong table would not be.
        """
        candidates = sorted(
            name
            for name in allowed_objects
            if (bare := name.split(".", 1)[-1].lower())
            in ("date_dim", "dim_date", "d_date", "dates", "date_dimension")
            or bare.endswith("_date_dim")
        )
        return candidates[0] if candidates else None
