"""Cadence et paramètres du pipeline TikTok.

Format court : cadence plus soutenue que YouTube (2 shorts / semaine),
cohérente avec l'usage habituel de la plateforme. Pas de fenêtre horaire
figée pour l'instant — la publication reste manuelle (ARCHITECTURE.md §4).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostingSpec:
    posts_per_week: int
    drafts_per_run: int = 1
    preferred_weekday: int | None = None
    preferred_hour: int | None = None


TIKTOK_SPEC = PostingSpec(posts_per_week=2, drafts_per_run=1)
