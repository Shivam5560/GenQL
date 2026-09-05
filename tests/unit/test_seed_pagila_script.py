"""Static checks on data/seed_pagila.sh.

The script has never been executed in this environment (no local psql
client — see data/README.md), so it cannot be covered by an integration
test. These checks instead prove, by inspecting the script text, that the
two defects from final-review.md I6 are fixed: PGOPTIONS alone cannot target
the `pagila` schema against the current pg_dump-shaped dump (every statement
is schema-qualified as `public.<name>`, which overrides search_path), and a
mid-file psql failure must abort the script rather than exit 0.
"""

from __future__ import annotations

import pathlib

SCRIPT = pathlib.Path(__file__).parent.parent.parent / "data" / "seed_pagila.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_every_psql_invocation_that_runs_dump_files_stops_on_error() -> None:
    text = _text()
    for line in text.splitlines():
        if "-f " in line and "psql" in line:
            assert "-v ON_ERROR_STOP=1" in line, f"missing ON_ERROR_STOP: {line}"


def test_the_dump_is_rewritten_to_target_the_pagila_schema_before_running() -> None:
    text = _text()
    # The fix rewrites the dump's `public.` schema qualifier to `pagila.`
    # *before* any psql invocation runs it, since PGOPTIONS alone does not
    # override a schema-qualified dump.
    rewrite_index = text.index("sed")
    assert "public" in text[rewrite_index : rewrite_index + 200]
    assert "pagila" in text[rewrite_index : rewrite_index + 200]

    first_dump_run_index = text.index('-f "$TMP')
    assert rewrite_index < first_dump_run_index


def test_readme_marks_pagila_as_unverified() -> None:
    """final-review.md I6/triage item 4: Pagila must not be presented as an
    equally-available seed until it has actually been run."""
    readme = (
        (pathlib.Path(__file__).parent.parent.parent / "data" / "README.md")
        .read_text(encoding="utf-8")
        .lower()
    )
    pagila_line = next(line for line in readme.splitlines() if "pagila" in line)
    assert "unverified" in pagila_line
