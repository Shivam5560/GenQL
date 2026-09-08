"""Rendering helpers shared by every CandidateGenerationStrategy — the
schema-link catalog and the few-shot example block look identical regardless
of which strategy's instructions wrap them."""

from __future__ import annotations

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.schema_link import SchemaLink


def render_link(link: SchemaLink) -> str:
    parts = [f"- {link.object_qualified_name}"]
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
