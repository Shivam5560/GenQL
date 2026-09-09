"""Accepts one rating, refusing a correction that is not a SELECT.

A service rather than the controller calling the port directly, because
"controllers hold no business logic" is a rule this codebase keeps without
exception — and this is business logic: the corrected SQL is the seed of a
future retrieval index, and nothing else in the system will ever validate it.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from genql.domain.entities.feedback import Feedback
from genql.domain.errors import FeedbackError
from genql.domain.ports.feedback_writer import FeedbackWriter


class FeedbackService:
    def __init__(self, writer: FeedbackWriter) -> None:
        self._writer = writer

    def record(self, feedback: Feedback) -> None:
        if feedback.corrected_sql is not None:
            self._require_select(feedback.corrected_sql)
        self._writer.write(feedback)

    @staticmethod
    def _require_select(sql: str) -> None:
        try:
            parsed = sqlglot.parse_one(sql, dialect="postgres")
        except sqlglot.errors.ParseError as exc:
            raise FeedbackError(f"the corrected SQL does not parse: {exc}") from exc
        if not isinstance(parsed, exp.Select | exp.Union) and parsed.find(exp.Select) is None:
            raise FeedbackError("the corrected SQL must be a SELECT statement")
