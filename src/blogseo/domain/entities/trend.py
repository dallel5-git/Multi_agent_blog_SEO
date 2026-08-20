"""Entités de veille : `TrendItem` (signal brut) et `TrendDigest` (agrégat)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class TrendOrigin(str, Enum):
    """Provenance du signal, pour pondérer et tracer les sources."""

    GLOBAL_TECH = "global_tech"   # Hacker News, Reddit, dev.to, Product Hunt
    TUNISIA = "tunisia"           # médias / écosystème tech tunisien
    SEARCH_TRENDS = "search_trends"  # Google Trends (pytrends)
    WEB_SEARCH = "web_search"     # DuckDuckGo / Tavily


@dataclass(frozen=True, slots=True)
class TrendItem:
    """Un signal de veille unitaire, normalisé quelle que soit sa source."""

    title: str
    url: str
    source: str                 # nom lisible : "Hacker News", "r/n8n", "Managers.tn"...
    origin: TrendOrigin
    summary: str = ""
    score: float = 0.0          # popularité brute (upvotes, réactions, intérêt Trends)
    published_at: datetime | None = None
    keywords: tuple[str, ...] = ()

    @property
    def age_hours(self) -> float | None:
        if self.published_at is None:
            return None
        now = datetime.now(UTC)
        published = self.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        return (now - published).total_seconds() / 3600

    def as_context_line(self) -> str:
        """Ligne compacte injectée dans le prompt du Keyword Analyst."""
        head = f"[{self.source}] {self.title}"
        if self.score:
            head += f" (score {self.score:g})"
        if self.summary:
            head += f" — {self.summary[:200]}"
        return f"{head} <{self.url}>"


@dataclass(slots=True)
class TrendDigest:
    """Résultat d'un agent de veille : une liste de signaux + des métadonnées."""

    origin: TrendOrigin
    items: list[TrendItem] = field(default_factory=list)
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    errors: list[str] = field(default_factory=list)

    def top(self, limit: int = 10) -> list[TrendItem]:
        return sorted(self.items, key=lambda i: i.score, reverse=True)[:limit]

    def as_context_block(self, limit: int = 10) -> str:
        if not self.items:
            return "(aucun signal collecté)"
        return "\n".join(item.as_context_line() for item in self.top(limit))

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.items)
