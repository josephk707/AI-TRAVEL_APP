"""Repository for `phrasebook_entries` — F10 static Local Phrase Assistant
(DATABASE_SCHEMA.md §5)."""

from __future__ import annotations

from typing import Any

from app.repositories.base import Repository


class PhrasebookRepository(Repository):
    async def list_for_region(
        self, region: str, language: str | None = None, category: str | None = None
    ) -> list[dict[str, Any]]:
        rows = await self.fetch(
            """
            select id, region, language_code, category, phrase_en,
                   phrase_local_script, phrase_transliteration, audio_url, created_at
            from public.phrasebook_entries
            where region ilike $1
              and ($2::text is null or language_code = $2)
              and ($3::text is null or category = $3)
            order by category, phrase_en;
            """,
            region,
            language,
            category,
        )
        return [dict(row) for row in rows]
