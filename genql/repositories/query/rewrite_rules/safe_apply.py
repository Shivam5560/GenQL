"""One place where a sqlglot optimizer pass is made to honour the RewriteRule
contract.

The port promises a rule never raises and always returns an expression.
sqlglot's passes raise OptimizeError on input they cannot resolve — a
correlated reference they cannot scope, an unqualified column that survived
validation — and a rewrite that cannot run is not a turn-ending failure: the
statement is already correct, it just does not get faster. Swallowing here
keeps that judgment in one file instead of four.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError


def safe_apply(
    pass_fn: Callable[[exp.Expression], exp.Expression], expression: exp.Expression
) -> exp.Expression:
    try:
        return pass_fn(expression)
    except (OptimizeError, ParseError):
        return expression
