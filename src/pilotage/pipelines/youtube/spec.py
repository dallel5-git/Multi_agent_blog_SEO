"""Cadence et paramètres du pipeline YouTube.

Cadence fixée par l'auteur : 1 vidéo / semaine, pas de fenêtre horaire figée
pour l'instant (`preferred_weekday`/`preferred_hour` restent `None` — la
publication reste manuelle, voir ARCHITECTURE.md §4).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostingSpec:
    posts_per_week: int
    drafts_per_run: int = 1
    preferred_weekday: int | None = None  # 0 = lundi … 6 = dimanche
    preferred_hour: int | None = None


YOUTUBE_SPEC = PostingSpec(posts_per_week=1, drafts_per_run=1)
