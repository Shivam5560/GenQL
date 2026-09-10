"""Rendering helpers shared by every CandidateGenerationStrategy — the
schema-link catalog and the few-shot example block look identical regardless
of which strategy's instructions wrap them."""

from __future__ import annotations

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.value_objects.surrogate_keys import (
    SURROGATE_KEY_GUIDANCE,
    uses_surrogate_keys,
)


def render_schema_conventions(links: tuple[SchemaLink, ...]) -> str:
    """Facts about how this schema is shaped, when they apply to it.

    Empty against a schema that does not use surrogate keys — see
    `genql.domain.value_objects.surrogate_keys` for why that is conditional
    rather than always-on.
    """
    columns = (name for link in links for name in link.column_names)
    return SURROGATE_KEY_GUIDANCE if uses_surrogate_keys(columns) else ""


def render_link(link: SchemaLink) -> str:
    parts = [f"- {link.schema_qualified_name}"]
    if link.column_names:
        parts.append(f"    columns: {', '.join(link.column_names)}")
    if link.join_paths:
        parts.append(f"    join paths: {', '.join(link.join_paths)}")
    return "\n".join(parts)


def render_examples(examples: tuple[AmbiguityExample, ...]) -> str:
    if not examples:
        return ""
    rendered = "\n\n".join(
        f"Q: {e.question}\nInterpretations: {'; '.join(e.interpretations)}\n"
        f"Resolved: {e.resolution}"
        for e in examples
    )
    return f"\n\nSimilar ambiguous questions resolved previously:\n{rendered}"
