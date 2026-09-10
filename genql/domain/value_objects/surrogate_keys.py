"""What a `_sk` column is, said once, for every prompt that needs to say it.

Both the planner (a service) and the candidate generators (repositories) have
to warn the model off casting a surrogate key to a date, and a service may not
import a repository — so the sentence lives in the domain, where both may read
it, rather than being copied into two prompts that then drift apart.

It is emitted only when the linked schema actually uses the convention.
Against a schema with no `_sk` columns the guidance is noise in every prompt of
every turn, and a prompt line that is usually irrelevant trains the reader —
model or human — to skip the block it sits in.

`SurrogateKeyDateGuardrail` enforces this statically. The prompt is the cheap
half of the same rule: catching it here costs nothing, catching it there costs
a regeneration round trip.
"""

from __future__ import annotations

from collections.abc import Iterable

SURROGATE_KEY_SUFFIX = "_sk"

SURROGATE_KEY_GUIDANCE = (
    "This schema is dimensionally modelled: a column ending in `_sk` is a surrogate "
    "key — an opaque row id in a dimension table — not a value and never a date. "
    "`ss_sold_date_sk` does not hold 20240115; it holds a row id like 2452642. To "
    "filter or group by time, JOIN the date dimension on the key "
    "(`... JOIN date_dim d ON d.d_date_sk = f.ss_sold_date_sk`) and use that table's "
    "real date columns. Casting, formatting, or doing interval arithmetic on a `_sk` "
    "column is always wrong and the statement will be rejected."
)


def uses_surrogate_keys(column_names: Iterable[str]) -> bool:
    return any(name.lower().endswith(SURROGATE_KEY_SUFFIX) for name in column_names)
