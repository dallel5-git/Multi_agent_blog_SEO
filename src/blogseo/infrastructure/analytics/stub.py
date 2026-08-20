"""Adapter Analytics — stub v1.

Le port est déjà figé (`AnalyticsPort`). Cet adapter :
1. lit un fichier optionnel `storage/analytics/performance.json` si l'auteur y
   dépose un export manuel de Search Console (aucune clé requise) ;
2. sinon, renvoie une liste vide et un feedback vide.

Brancher la vraie Search Console plus tard ne demandera qu'un nouvel adapter
implémentant le même port — aucun agent ni l'orchestrateur ne changeront.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from ...domain.ports.analytics import AnalyticsPort, ArticlePerformance, PerformanceFeedback

logger = logging.getLogger(__name__)


class FileAnalyticsStub(AnalyticsPort):
    """Ingestion depuis un export JSON déposé à la main (100 % gratuit)."""

    name = "analytics-stub"

    #: Format attendu :
    #: [{"slug": "...", "impressions": 120, "clicks": 8,
    #:   "average_position": 14.2, "top_queries": ["n8n tunisie", ...]}, ...]
    def __init__(self, data_file: Path) -> None:
        self.data_file = data_file

    def is_available(self) -> bool:
        return self.data_file.exists()

    def fetch_performance(self, *, days: int = 28) -> list[ArticlePerformance]:
        if not self.data_file.exists():
            logger.info(
                "Analytics : aucun export trouvé (%s) — le Keyword Analyst travaillera sans "
                "signal de performance.", self.data_file,
            )
            return []
        try:
            raw = json.loads(self.data_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Export analytics illisible : %s", exc)
            return []

        rows = raw.get("rows", raw) if isinstance(raw, dict) else raw
        performances = [
            ArticlePerformance(
                slug=row.get("slug", ""),
                impressions=int(row.get("impressions", 0)),
                clicks=int(row.get("clicks", 0)),
                average_position=float(row.get("average_position", 0.0)),
                top_queries=tuple(row.get("top_queries", []) or ()),
            )
            for row in rows
            if isinstance(row, dict) and row.get("slug")
        ]
        logger.info("Analytics : %s ligne(s) de performance chargée(s)", len(performances))
        return performances

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

        feedback = PerformanceFeedback(
            winning_keywords=winning[:10],
            underperforming_slugs=underperforming[:10],
            suggested_topics=list(dict.fromkeys(suggested))[:10],
            generated_at=date.today(),
        )
        logger.info(
            "Analytics : %s mot(s)-clé(s) gagnant(s), %s article(s) à retravailler",
            len(feedback.winning_keywords), len(feedback.underperforming_slugs),
        )
        return feedback
