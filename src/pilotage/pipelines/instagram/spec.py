"""Cadence et paramètres du pipeline Instagram.

Un carousel demande plus de préparation (template visuel personnalisé par
page) qu'un post simple : 1 carousel / semaine.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostingSpec:
    posts_per_week: int
    drafts_per_run: int = 1
    preferred_weekday: int | None = None
    preferred_hour: int | None = None


INSTAGRAM_SPEC = PostingSpec(posts_per_week=1, drafts_per_run=1)
