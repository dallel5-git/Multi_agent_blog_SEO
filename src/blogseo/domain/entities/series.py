"""Série d'articles liés entre eux (issue #41 « Mode série d'articles »).

Une série est planifiée en une fois par le Keyword Analyst (3 à 5 sujets
distincts autour d'un même thème), puis consommée un sujet par run normal du
pipeline. Le statut de chaque sujet suit son propre cycle :

    pending   → sujet planifié, pas encore traité
    written   → article écrit dans le blog (dry-run ou décision REJECT
                inclus) : ne doit plus être resservi par la file d'attente
    published → article réellement poussé sur Git : seul ce statut rend le
                sujet éligible au maillage retour vers les articles suivants
    skipped   → sujet planifié devenu un doublon entre-temps, abandonné
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from ..value_objects.category import Category


@dataclass(slots=True)
class SeriesTopic:
    """Un sujet planifié au sein d'une série."""

    title: str
    angle: str
    category: Category
    primary_keyword: str
    secondary_keywords: tuple[str, ...] = ()
    outline: tuple[str, ...] = ()
    rationale: str = ""
    status: str = "pending"
    slug: str = ""

    @property
    def is_published(self) -> bool:
        return self.status == "published"


@dataclass(slots=True)
class ArticleSeries:
    """Une série de 3 à 5 articles liés, planifiée en une fois."""

    theme: str
    title: str
    topics: list[SeriesTopic]
    series_id: str = field(default_factory=lambda: f"serie-{uuid.uuid4().hex[:10]}")
    created_at: datetime = field(default_factory=datetime.now)

    def next_pending(self) -> SeriesTopic | None:
        for topic in self.topics:
            if topic.status == "pending":
                return topic
        return None

    def published_topics(self) -> list[SeriesTopic]:
        """Sujets réellement publiés (Git poussé), dans l'ordre de la série."""
        return [t for t in self.topics if t.status == "published"]

    @property
    def is_active(self) -> bool:
        return self.next_pending() is not None

    def summary(self) -> str:
        done = len(self.published_topics())
        return f"« {self.title} » — {done}/{len(self.topics)} article(s) publié(s)"
