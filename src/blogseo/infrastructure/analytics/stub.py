"""Adapter Analytics — stub / repli manuel.

Le port est déjà figé (`AnalyticsPort`). Cet adapter :
1. lit un fichier optionnel `storage/analytics/performance.json` si l'auteur y
   dépose un export manuel (aucune clé requise) ;
2. sinon, renvoie une liste vide et un feedback vide.

Sert aussi de repli quand `SearchConsoleAnalytics` n'est pas configuré (voir
`infrastructure/analytics/search_console.py`) — les deux adapters partagent la
même règle `build_feedback`, héritée de `AnalyticsPort`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ...domain.ports.analytics import AnalyticsPort, ArticlePerformance

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
