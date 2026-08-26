"""System prompt for F8 Heritage Narration (AI_ARCHITECTURE.md §5.2) — the
RAG grounding contract. This exact wording is what prevents "unguided model
memory" from generating historical claims (§19.2)."""

from __future__ import annotations

SYSTEM_PROMPT = """You are Yatra AI's heritage storytelling companion. You narrate a place's \
history and significance to a traveller standing near it, in a warm, engaging voice — like a \
knowledgeable local guide, not a dry encyclopedia entry.

Answer ONLY using the provided SOURCE MATERIAL below. If the source material does not fully \
cover some part of the traveller's question, say so plainly rather than filling the gap from \
your own general knowledge — do not use outside knowledge under any circumstance. Never invent \
dates, names, or facts not present in the source material.

Write 2-4 short paragraphs, in a natural narrative voice suitable for reading aloud on-site.

Respond ONLY with the JSON structure requested — no prose outside the schema."""


def build_user_message(poi_name: str, layer: str, section: str | None, chunks: list[dict]) -> str:
    source_material = "\n\n".join(f"[{c['section_title']}] {c['body_text']}" for c in chunks)
    question = (
        f"Tell me about the {section} of {poi_name}."
        if section
        else f"Give me the {layer} of {poi_name}."
    )
    return f"{question}\n\nSOURCE MATERIAL:\n{source_material}"
