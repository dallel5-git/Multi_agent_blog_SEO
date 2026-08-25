"""Entités Python du calendrier partagé (miroir des tables de `schema.sql`).

Les trois énumérations d'état sont volontairement `class X(str, Enum)`, jamais
`StrEnum` (voir la note `UP042` de `pyproject.toml`) : les valeurs partent
telles quelles en base SQLite et dans les `callback_data` Telegram.

`ContentStatus` doit rester synchronisée avec la contrainte `CHECK` de
`content_items.status` dans `schema.sql` — un test dédié
(`tests/unit/test_shared_calendar.py`) vérifie que les deux acceptent
exactement les mêmes valeurs, pour qu'ajouter un état oblige à toucher les
deux endroits à la fois.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..platforms import Platform


class ContentStatus(str, Enum):
    """Les sept états du cycle de vie d'un contenu — colonnes du Kanban.

    idea → drafted → pending_review → approved → published → archived
    (`rejected` est un état terminal, atteignable depuis `pending_review`)
    """

    IDEA = "idea"
    DRAFTED = "drafted"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class CrossRefState(str, Enum):
    """État de la mention croisée SUGGÉRÉE d'un `content_item` vers un autre."""

    NONE = "none"
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class StatSource(str, Enum):
    """Distingue une mesure d'API d'une saisie manuelle (X, TikTok)."""

    API = "api"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class ContentItem:
    """Une idée de contenu, quelle que soit la plateforme."""

    platform: Platform
    title: str
    topic: str | None = None
    body: str | None = None
    status: ContentStatus = ContentStatus.IDEA
    cross_ref_id: int | None = None
    cross_ref_state: CrossRefState = CrossRefState.NONE
    scheduled_for: str | None = None
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class PlatformPost:
    """Une publication réelle, avec son lien — créée après validation manuelle."""

    content_item_id: int
    platform: Platform
    url: str
    published_at: str
    external_id: str | None = None
    id: int | None = None
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class StatSnapshot:
    """Une mesure d'audience à un instant t. On accumule, jamais on n'écrase."""

    platform: Platform
    platform_post_id: int | None = None
    source: StatSource = StatSource.API
    captured_at: str | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    followers: int | None = None
    affiliate_clicks: int | None = None
    sales: int | None = None
    revenue_tnd: float | None = None
    id: int | None = None
