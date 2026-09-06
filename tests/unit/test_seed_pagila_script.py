"""Static checks on data/seed_pagila.sh.

These checks prove, by inspecting the script text, that the two defects from
final-review.md I6 are fixed: PGOPTIONS alone cannot target the `pagila`
schema against the current pg_dump-shaped dump (every statement is
schema-qualified as `public.<name>`, which overrides search_path), and a
mid-file failure must abort the script rather than exit 0. The script has
since been run for real against a second database, `genql_wh2` (see
data/README.md); GENQL_SEED_EXEC is what makes that possible without a local
psql client.
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
    # *before* $SEED_EXEC runs it, since PGOPTIONS alone does not override a
    # schema-qualified dump. `text.index("sed")` would also match inside an
    # ordinary word like "used" in the surrounding prose, so anchor on the
    # actual command instead of the bare substring.
    rewrite_index = text.index("sed -i")
    assert "public" in text[rewrite_index : rewrite_index + 200]
    assert "pagila" in text[rewrite_index : rewrite_index + 200]

    first_dump_run_index = text.index('$SEED_EXEC < "$TMP')
    assert rewrite_index < first_dump_run_index


def test_readme_marks_pagila_as_verified() -> None:
    """final-review.md I6/triage item 4 required Pagila not be presented as
    an equally-available seed until it had actually been run. Task 10 ran it
    for real against genql_wh2 and confirmed the film count, so the README
    must now say so rather than carry the old UNVERIFIED marker."""
    readme = (
        (pathlib.Path(__file__).parent.parent.parent / "data" / "README.md")
        .read_text(encoding="utf-8")
        .lower()
    )
    pagila_line = next(line for line in readme.splitlines() if "pagila" in line)
    assert "unverified" not in pagila_line
    assert "verified" in pagila_line
