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
    """Contrat d'ingestion des données de performance.

    `build_feedback` est une implémentation concrète, pas un détail d'adapter :
    la règle métier (mots-clés gagnants, articles sous-performants, pistes en
    position 11-30) doit être identique quelle que soit la source des données
    brutes (export manuel, Search Console, Plausible…), donc elle vit ici plutôt
    que d'être dupliquée dans chaque adapter.
    """

    name: str = "analytics"

    @abstractmethod
    def fetch_performance(self, *, days: int = 28) -> list[ArticlePerformance]:
        """Récupère les performances des articles sur la fenêtre demandée."""

    def build_feedback(self, performances: list[ArticlePerformance]) -> PerformanceFeedback:
        """Transforme les performances brutes en consignes pour le Keyword Analyst."""
        if not performances:
            return PerformanceFeedback(generated_at=date.today())

        # Mots-clés « gagnants » : requêtes des articles avec le meilleur CTR.
        best = sorted(performances, key=lambda p: p.ctr, reverse=True)[:3]
        winning: list[str] = []
        for perf in best:
            winning.extend(q for q in perf.top_queries[:3] if q not in winning)

        # Sous-performants : beaucoup d'impressions mais très peu de clics.
        underperforming = [
            p.slug for p in performances
            if p.impressions >= 100 and p.ctr < 0.01
        ]

        # Pistes : requêtes en position 11-30 (page 2), à portée d'un article dédié.
        suggested = [
            query
            for perf in performances if 10 < perf.average_position <= 30
            for query in perf.top_queries[:2]
        ]

        return PerformanceFeedback(
            winning_keywords=winning[:10],
            underperforming_slugs=underperforming[:10],
            suggested_topics=list(dict.fromkeys(suggested))[:10],
            generated_at=date.today(),
        )

    def is_available(self) -> bool:
        return False
