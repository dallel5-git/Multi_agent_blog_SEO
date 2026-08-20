"""Port `AnalyticsPort` : ingestion différée des performances (stub v1).

L'agent Analytics Tracker est volontairement un stub dans la v1 : le contrat est
figé dès maintenant pour que brancher Search Console / Plausible plus tard ne
demande qu'un nouvel adapter, sans toucher aux agents ni à l'orchestrateur.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class ArticlePerformance:
    """Performance d'un article sur une période."""

    slug: str
    impressions: int = 0
    clicks: int = 0
    average_position: float = 0.0
    top_queries: tuple[str, ...] = ()
    period_start: date | None = None
    period_end: date | None = None

    @property
    def ctr(self) -> float:
        return round(self.clicks / self.impressions, 4) if self.impressions else 0.0


@dataclass(slots=True)
class PerformanceFeedback:
    """Signal renvoyé au Keyword Analyst pour orienter les prochains sujets."""

    winning_keywords: list[str] = field(default_factory=list)
    underperforming_slugs: list[str] = field(default_factory=list)
    suggested_topics: list[str] = field(default_factory=list)
    generated_at: date | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.winning_keywords or self.underperforming_slugs or self.suggested_topics)

    def as_context_block(self) -> str:
        if self.is_empty:
            return "(aucune donnée de performance disponible pour l'instant)"
        return (
            f"Mots-clés performants : {', '.join(self.winning_keywords) or '—'}\n"
            f"Articles sous-performants : {', '.join(self.underperforming_slugs) or '—'}\n"
            f"Pistes suggérées : {', '.join(self.suggested_topics) or '—'}"
        )


class AnalyticsPort(ABC):
    """Contrat d'ingestion des données de performance."""

    name: str = "analytics"

    @abstractmethod
    def fetch_performance(self, *, days: int = 28) -> list[ArticlePerformance]:
        """Récupère les performances des articles sur la fenêtre demandée."""

    @abstractmethod
    def build_feedback(self, performances: list[ArticlePerformance]) -> PerformanceFeedback:
        """Transforme les données brutes en signal exploitable par le Keyword Analyst."""

    def is_available(self) -> bool:
        return False
