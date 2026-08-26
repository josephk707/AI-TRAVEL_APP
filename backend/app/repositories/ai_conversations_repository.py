"""Repository for `ai_conversations`/`ai_messages` (F5 conversational
modification history, DATABASE_SCHEMA.md §10) and `feedback_signals`
(Personalization Engine input, AI_ARCHITECTURE.md §7.2 — an
`explicit_correction` signal is written synchronously, never queued, per
the one hard rule that section calls out twice)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.repositories.base import Repository


class AiConversationsRepository(Repository):
    async def get_or_create_conversation(self, user_id: str, trip_id: str) -> str:
        uid, tid = uuid.UUID(user_id), uuid.UUID(trip_id)
        existing = await self.fetchval(
            "select id from public.ai_conversations where user_id = $1 and trip_id = $2 "
            "order by started_at desc limit 1;",
            uid,
            tid,
        )
        if existing is not None:
            return str(existing)
        created = await self.fetchval(
            "insert into public.ai_conversations (user_id, trip_id) values ($1, $2) returning id;",
            uid,
            tid,
        )
        return str(created)

    async def log_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        model: str | None = None,
        tokens_used: int | None = None,
        confidence: str | None = None,
    ) -> None:
        await self.fetchval(
            """
            insert into public.ai_messages
                (conversation_id, context_type, role, content, model, tokens_used, confidence)
            values ($1, 'chat', $2, $3, $4, $5, $6)
            returning id;
            """,
            uuid.UUID(conversation_id),
            role,
            content,
            model,
            tokens_used,
            confidence,
        )

    async def get_recent_messages(
        self, conversation_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        rows = await self.fetch(
            "select role, content, created_at from public.ai_messages "
            "where conversation_id = $1 order by created_at desc limit $2;",
            uuid.UUID(conversation_id),
            limit,
        )
        return list(reversed([dict(row) for row in rows]))

    async def log_photo_qa(
        self, *, content: str, role: str, model: str | None, confidence: str | None
    ) -> None:
        """Visual Q&A (F9) is a single-shot, non-conversational endpoint —
        `conversation_id` stays NULL, `context_type='photo_qa'` (the M8 fix
        recorded in DATABASE_SCHEMA.md §10)."""
        await self.fetchval(
            """
            insert into public.ai_messages
                (conversation_id, context_type, role, content, model, confidence)
            values (null, 'photo_qa', $1, $2, $3, $4)
            returning id;
            """,
            role,
            content,
            model,
            confidence,
        )


class FeedbackRepository(Repository):
    async def log_signal(
        self,
        user_id: str,
        *,
        trip_id: str | None,
        itinerary_item_id: str | None,
        signal_type: str,
        value: dict[str, Any] | None = None,
    ) -> None:
        await self.fetchval(
            """
            insert into public.feedback_signals
                (user_id, trip_id, itinerary_item_id, signal_type, value)
            values ($1, $2, $3, $4, $5::jsonb)
            returning id;
            """,
            uuid.UUID(user_id),
            uuid.UUID(trip_id) if trip_id else None,
            uuid.UUID(itinerary_item_id) if itinerary_item_id else None,
            signal_type,
            json.dumps(value or {}),
        )
