"""Source de veille : dev.to via l'API publique `/api/articles` (gratuite, sans clé)."""

from __future__ import annotations

import logging
from datetime import datetime

import requests

from ...domain.entities.trend import TrendItem, TrendOrigin
from ...domain.ports.search import TechSourcePort

logger = logging.getLogger(__name__)

_ENDPOINT = "https://dev.to/api/articles"


class DevToSource(TechSourcePort):
    """Articles populaires de dev.to sur les tags configurés."""

    name = "dev.to"

    def __init__(
        self,
        tags: tuple[str, ...] | list[str] = ("ai", "automation", "python"),
        *,
        limit: int = 20,
        timeout_s: int = 20,
        user_agent: str = "blogseo/1.0",
        top_days: int = 7,
    ) -> None:
        self.tags = list(tags)
        self.limit = limit
        self.timeout_s = timeout_s
        self.top_days = top_days
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def fetch(self, *, limit: int | None = None) -> list[TrendItem]:
        per_tag = max(3, (limit or self.limit) // max(1, len(self.tags)) + 2)
        items: list[TrendItem] = []
        for tag in self.tags:
            items.extend(self._fetch_tag(tag, per_tag))
        items.sort(key=lambda i: i.score, reverse=True)
        result = items[: (limit or self.limit)]
        logger.info("[dev.to] %s signal(aux) sur %s tag(s)", len(result), len(self.tags))
        return result

    def _fetch_tag(self, tag: str, limit: int) -> list[TrendItem]:
        try:
            response = self._session.get(
                _ENDPOINT,
                params={"tag": tag, "top": self.top_days, "per_page": limit},
                timeout=self.timeout_s,
            )
            if response.status_code >= 400:
                logger.warning("dev.to tag=%s → HTTP %s", tag, response.status_code)
                return []
            articles = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("dev.to tag=%s injoignable : %s", tag, exc)
            return []

        items: list[TrendItem] = []
        for article in articles:
            published_at = None
            raw_date = article.get("published_at")
            if raw_date:
                try:
                    published_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except ValueError:
                    published_at = None
            items.append(
                TrendItem(
                    title=(article.get("title") or "").strip(),
                    url=article.get("url", ""),
                    source=f"dev.to/{tag}",
                    origin=TrendOrigin.GLOBAL_TECH,
                    summary=(article.get("description") or "").strip(),
                    score=float(article.get("positive_reactions_count", 0)),
                    published_at=published_at,
                    keywords=tuple(article.get("tag_list", []) or ()),
                )
            )
        return items
