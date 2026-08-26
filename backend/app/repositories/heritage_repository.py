"""
Repository for `heritage_content`/`heritage_content_embeddings` — F8
Heritage Narration RAG Pipeline (AI_ARCHITECTURE.md §5,
DATABASE_SCHEMA.md §5). `heritage_content_embeddings` has NO client-facing
RLS policy at all (the L9 fix) — only this backend's service-role
connection may read it, never the mobile client directly.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository


class HeritageRepository(Repository):
    async def get_published_content(
        self, poi_id: str, layer: str | None = None
    ) -> list[dict[str, Any]]:
        if layer:
            rows = await self.fetch(
                "select id, section_title, body_text, source_citation from public.heritage_content "
                "where poi_id = $1 and layer = $2 and is_published order by created_at asc;",
                uuid.UUID(poi_id),
                layer,
            )
        else:
            rows = await self.fetch(
                "select id, section_title, body_text, source_citation from public.heritage_content "
                "where poi_id = $1 and is_published order by created_at asc;",
                uuid.UUID(poi_id),
            )
        return [dict(row) for row in rows]

    async def has_any_published_content(self, poi_id: str) -> bool:
        value = await self.fetchval(
            "select exists (select 1 from public.heritage_content "
            "where poi_id = $1 and is_published);",
            uuid.UUID(poi_id),
        )
        return bool(value)

    async def vector_search(
        self, poi_id: str, layer: str, query_embedding: list[float], top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Cosine-similarity search over this POI's published, embedded
        chunks. Returns rows ordered nearest-first, each carrying a
        `similarity` in [0, 1] (1 - cosine distance) so the caller can
        derive a structural confidence flag from retrieval quality
        (AI_ARCHITECTURE.md §5.2 step 4) rather than asking the LLM."""
        vector_literal = "[" + ",".join(str(v) for v in query_embedding) + "]"
        rows = await self.fetch(
            """
            select hc.section_title, e.chunk_text, hc.source_citation,
                   1 - (e.embedding <=> $4::vector) as similarity
            from public.heritage_content_embeddings e
            join public.heritage_content hc on hc.id = e.heritage_content_id
            where hc.poi_id = $1 and hc.layer = $2 and hc.is_published
            order by e.embedding <=> $4::vector
            limit $3;
            """,
            uuid.UUID(poi_id),
            layer,
            top_k,
            vector_literal,
        )
        return [dict(row) for row in rows]
