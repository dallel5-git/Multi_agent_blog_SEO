"""Ports de collecte d'information : recherche web, tendances, flux tech."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..entities.trend import TrendItem


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Résultat de recherche web normalisé."""

    title: str
    url: str
    snippet: str = ""
    source: str = ""

    def as_context_line(self) -> str:
        return f"- {self.title} — {self.snippet[:200]} <{self.url}>"


class SearchPort(ABC):
    """Contrat de recherche web (implémentation par défaut : DuckDuckGo)."""

    name: str = "search"

    @abstractmethod
    def search(self, query: str, *, max_results: int = 8, region: str = "fr-fr") -> list[SearchResult]:
        """Recherche générique. Doit renvoyer une liste vide plutôt que lever, si possible."""

    def search_news(self, query: str, *, max_results: int = 8, region: str = "fr-fr") -> list[SearchResult]:
        """Recherche d'actualité. Par défaut, retombe sur `search`."""
        return self.search(query, max_results=max_results, region=region)

    def is_available(self) -> bool:
        return True


class TrendsPort(ABC):
    """Contrat d'accès aux tendances de recherche (implémentation : pytrends)."""

    name: str = "trends"

    @abstractmethod
    def interest_over_time(self, keywords: list[str], *, geo: str = "TN", timeframe: str = "now 7-d") -> dict[str, float]:
        """Intérêt moyen par mot-clé sur la période, normalisé 0-100."""

    @abstractmethod
    def related_queries(self, keyword: str, *, geo: str = "TN") -> list[str]:
        """Requêtes associées et montantes."""

    def is_available(self) -> bool:
        return True


class TechSourcePort(ABC):
    """Contrat d'une source de veille tech (Hacker News, Reddit, dev.to, RSS...)."""

    name: str = "source"

    @abstractmethod
    def fetch(self, *, limit: int = 20) -> list[TrendItem]:
        """Récupère les signaux récents. Ne doit jamais lever : renvoyer [] si indisponible."""
