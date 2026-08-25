"""Cadence et paramètres du pipeline X.

Format texte, peu coûteux à produire : cadence plus soutenue (3 posts /
semaine).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostingSpec:
    posts_per_week: int
    drafts_per_run: int = 1
    preferred_weekday: int | None = None
    preferred_hour: int | None = None


X_SPEC = PostingSpec(posts_per_week=3, drafts_per_run=1)
