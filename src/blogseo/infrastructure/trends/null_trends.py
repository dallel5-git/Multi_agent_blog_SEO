"""Adapter neutre de `TrendsPort`, utilisé en mode `--offline`.

Renvoie toujours des résultats vides, sans appeler Google Trends.
"""

from __future__ import annotations

from ...domain.ports.search import TrendsPort


class NullTrends(TrendsPort):
    """Aucun signal Trends : utilisé quand le pipeline tourne hors ligne."""

    name = "null-trends"

    def interest_over_time(self, keywords: list[str], *, geo: str = "TN", timeframe: str = "now 7-d") -> dict[str, float]:
        return {}

    def related_queries(self, keyword: str, *, geo: str = "TN") -> list[str]:
        return []

    def is_available(self) -> bool:
        return False
