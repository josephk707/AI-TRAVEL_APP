"""
Chunks and embeds every published `heritage_content` row that doesn't yet
have embeddings, via the real Gemini embedding model
(AI_ARCHITECTURE.md §5.1 step 2). Required for section-level semantic
narration navigation ("tell me about the carvings near the entrance") —
the plain poi_id+layer overview retrieval path does NOT need this and
works without it (AI_ARCHITECTURE.md §5.2 step 1).

BLOCKED in this environment until a real GEMINI_API_KEY is configured in
backend/.env — this script fails closed with a clear message rather than
silently doing nothing, per CLAUDE.md §9.

Usage:
    python scripts/embed_heritage_content.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(dotenv_path=REPO_ROOT / "backend" / ".env")

_CHUNK_TARGET_CHARS = 1600  # ~300-500 tokens, per AI_ARCHITECTURE.md §5.1


def _chunk_text(text: str) -> list[str]:
    """Sentence-boundary-aware chunking so a chunk never straddles a
    section it can't stand alone as a citation for (AI_ARCHITECTURE.md
    §5.1 step 2a)."""
    sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}." if current else f"{sentence}."
        if len(candidate) > _CHUNK_TARGET_CHARS and current:
            chunks.append(current.strip())
            current = f"{sentence}."
        else:
            current = candidate
    if current:
        chunks.append(current.strip())
    return chunks or [text]


async def main() -> int:
    from app.core.config import get_settings
    from app.services.ai.factory import get_llm_gateway

    settings = get_settings()
    if settings.gemini_api_key is None:
        print(
            "BLOCKED: GEMINI_API_KEY is not configured in backend/.env — "
            "cannot generate real embeddings. Add the key and re-run this script."
        )
        return 1

    gateway = get_llm_gateway()
    assert gateway is not None

    database_url = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(
            """
            select hc.id, hc.body_text from public.heritage_content hc
            where hc.is_published
              and not exists (
                select 1 from public.heritage_content_embeddings e
                where e.heritage_content_id = hc.id
              );
            """
        )
        if not rows:
            print("Nothing to embed — every published row already has embeddings.")
            return 0

        total_chunks = 0
        for row in rows:
            chunks = _chunk_text(row["body_text"])
            embeddings = await gateway.embed(
                chunks, dimensions=settings.gemini_embedding_dimensions, task_type="RETRIEVAL_DOCUMENT"
            )
            for index, (chunk_text, vector) in enumerate(zip(chunks, embeddings.vectors, strict=True)):
                vector_literal = "[" + ",".join(str(v) for v in vector) + "]"
                await conn.execute(
                    """
                    insert into public.heritage_content_embeddings
                        (heritage_content_id, chunk_index, chunk_text, embedding)
                    values ($1, $2, $3, $4::vector);
                    """,
                    row["id"],
                    index,
                    chunk_text,
                    vector_literal,
                )
                total_chunks += 1
            print(f"  Embedded heritage_content {row['id']} — {len(chunks)} chunk(s).")

        print(f"\n{total_chunks} embedding row(s) inserted across {len(rows)} content row(s).")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
