"""Can anything in scope answer a "what time period?" question at all.

Its own module rather than a private helper inside ambiguity_gate_service,
partly to keep that file under the house length limit and partly because
this is a different kind of knowledge: everything here is a fact about how
warehouse columns get named, and nothing here knows what the gate does with
the answer.

A naming heuristic rather than a type check, because SchemaLink carries no
type information (genql.domain.entities.schema_link) — only names. That is
enough to tell "nothing in scope could possibly answer a time_range
question" from "maybe it could", which is all the caller needs: the gate
drops the dimension entirely in the first case rather than scoring it and
hoping a threshold catches it.
"""

from __future__ import annotations

from genql.domain.entities.schema_link import SchemaLink

_DATE_COLUMN_MARKERS = ("date", "_dt", "_yr", "year", "month", "quarter", "_dow")

# Dimension-table bookkeeping columns — TPC-DS's `s_rec_start_date` /
# `s_rec_end_date` (SCD2 row-validity tracking, present on every dimension
# table that carries history) and `s_closed_date_sk` (a one-off lifecycle
# event on the dimension row itself, not a transactional date) — match
# `_DATE_COLUMN_MARKERS` but are not a business date a generic question is
# asking about. Left unexcluded, a question with no real time dimension at
# all ("top 5 states by number of stores" against `tpcds.store`, which
# carries only these) still triggered the clarifying question this filter
# exists to remove. A question specifically about store openings/closures
# would still need to name that explicitly; this only decides whether to
# preemptively ask "what time period?" of a question that never mentioned
# time at all.
_SCD_BOOKKEEPING_MARKERS = ("rec_start", "rec_end", "closed_date")


def has_time_dimension(links: tuple[SchemaLink, ...]) -> bool:
    return any(
        marker in name.lower()
        for link in links
        for name in link.column_names
        if not any(scd in name.lower() for scd in _SCD_BOOKKEEPING_MARKERS)
        for marker in _DATE_COLUMN_MARKERS
    )
