"""Fail if any staged Python file exceeds the project line limit."""

from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 250


def main(paths: list[str]) -> int:
    failures: list[str] = []
    for raw in paths:
        path = Path(raw)
        if path.suffix != ".py" or not path.is_file():
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > LIMIT:
            failures.append(f"{path}: {lines} lines (limit {LIMIT})")
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
