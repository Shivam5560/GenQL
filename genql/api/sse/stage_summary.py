"""What one summariser returns, and the budget it has to say it in.

Separate from the summarisers themselves only because this package's files are
capped at 250 lines; the caps live here rather than beside `to_stage_event`
because they are what a summariser has to obey, and a summariser that has to
read the dispatcher to learn its own limits is a summariser nobody will keep
within them.

The budget is deliberately small. A stage's delta can carry every schema link
or every candidate statement, and the point of an event is to explain a
decision, not to mirror the state that produced it — so a fact is a label and a
short value, and there are at most ten of them. `detail` keeps the original
200-character line: it is what the CLI prints and what a narrow rail shows
before anyone expands anything, and widening it would widen every reading of
the stream at once.
"""

from __future__ import annotations

from typing import NamedTuple

MAX_DETAIL = 200
# Four hundred rather than two hundred: the one value that genuinely wants the
# room is the plan, which later stages check the SQL against — a reviewer needs
# the text critique had, not its first sentence. Ten of these is the worst case
# for a stage and the realistic case is two or three.
MAX_FACT_VALUE = 400
MAX_FACTS = 10


class StageSummary(NamedTuple):
    """One stage's reading of its own delta.

    `did_run` is false only for a stage that short-circuited — critique and
    probing on an uncontested turn, domain scoping when the caller named a
    domain. It becomes the event's `skipped` status, which is the distinction
    a reading client cannot make for itself.
    """

    detail: str | None
    facts: tuple[tuple[str, str], ...] = ()
    did_run: bool = True


def trim(text: str, limit: int) -> str:
    """Cut to `limit` characters, marking the cut so a truncated value never
    reads as a complete one."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"


def reported(detail: str, *facts: tuple[str, str]) -> StageSummary:
    """A stage that ran and has something to say about it.

    A fact with an empty value is dropped rather than rendered as a label with
    nothing beside it: most stages have facts that only exist on some paths —
    the narrowing suggestion, the guardrails that fired — and a caller that had
    to guard each one would say so ten times per module.
    """
    kept = tuple((label, trim(value, MAX_FACT_VALUE)) for label, value in facts if value)
    return StageSummary(trim(detail, MAX_DETAIL), kept[:MAX_FACTS])


def skipped(reason: str) -> StageSummary:
    """A stage the pipeline chose not to run, and why.

    The reason is the whole value of the event. Without it a skipped stage is
    just an absence, and an absence is what a reader mistakes for a failure.
    """
    return StageSummary(trim(reason, MAX_DETAIL), (), did_run=False)


def joined(pairs: tuple[tuple[str, object], ...], separator: str = " · ") -> str:
    """`(("entity", 0.96), ("metric", 0.31))` as `entity 0.96 · metric 0.31`.

    Every stage that reports per-dimension or per-candidate values wants the
    same shape, and one fact holding six readings is easier to read in a rail —
    and cheaper on the wire — than six facts holding one each.
    """
    return separator.join(f"{name} {value}" for name, value in pairs)
