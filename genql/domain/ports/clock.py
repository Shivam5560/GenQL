"""Wall-clock time as a dependency.

Ingestion records started/finished timestamps and per-step durations, and a
test asserting on those cannot race a real clock.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
