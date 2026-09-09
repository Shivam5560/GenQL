"""One hand-curated question and the statement whose result is its expectation.

The expectation is a reference SQL statement rather than literal rows: thirty
to fifty TPC-DS result sets pasted into YAML would be unreviewable and would
rot the first time the seed data was regenerated. Comparing the *results* of
two statements is still execution-result comparison — the generated SQL's text
is never inspected, which is what §15 actually forbids.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.failure_class import FailureClass


class GoldenCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    question: str
    datasource_name: str
    reference_sql: str
    failure_class: FailureClass
    domain_id: int | None = None
