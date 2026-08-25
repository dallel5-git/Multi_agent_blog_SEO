"""Cadence et paramètres du pipeline Facebook.

Audience Facebook tunisienne large mais moins technique (voir
`audience.technical_level_by_platform` du Brand Kernel) : 1 post / semaine,
pas de fenêtre horaire figée.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostingSpec:
    posts_per_week: int
    drafts_per_run: int = 1
    preferred_weekday: int | None = None
    preferred_hour: int | None = None


FACEBOOK_SPEC = PostingSpec(posts_per_week=1, drafts_per_run=1)
