"""Cadence et paramètres du pipeline du canal Telegram public.

Message léger à produire, mais un canal trop bavard fatigue ses abonnés :
1 message / semaine.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostingSpec:
    posts_per_week: int
    drafts_per_run: int = 1
    preferred_weekday: int | None = None
    preferred_hour: int | None = None


TELEGRAM_CHANNEL_SPEC = PostingSpec(posts_per_week=1, drafts_per_run=1)
