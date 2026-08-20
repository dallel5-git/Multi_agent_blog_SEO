"""Source de veille : Hacker News via l'API publique Firebase (gratuite, sans clé)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import requests

from ...domain.entities.trend import TrendItem, TrendOrigin
from ...domain.ports.search import TechSourcePort

logger = logging.getLogger(__name__)

_BASE = "https://hacker-news.firebaseio.com/v0"

# Mots-clés retenus : on ne garde que ce qui recoupe la ligne éditoriale du blog.
_RELEVANT_TERMS = (
    "ai", "llm", "gpt", "agent", "automation", "workflow", "n8n", "make.com",
    "python", "rag", "prompt", "openai", "gemini", "claude", "langchain",
    "no-code", "nocode", "self-host", "vector", "embedding", "mcp", "copilot",
)


class HackerNewsSource(TechSourcePort):
    """Top stories de Hacker News, filtrées sur les thèmes du blog."""

    name = "Hacker News"

    def __init__(self, *, limit: int = 20, timeout_s: int = 20, user_agent: str = "blogseo/1.0") -> None:
        self.limit = limit
        self.timeout_s = timeout_s
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def fetch(self, *, limit: int | None = None) -> list[TrendItem]:
        limit = limit or self.limit
        try:
            response = self._session.get(f"{_BASE}/topstories.json", timeout=self.timeout_s)
            response.raise_for_status()
            story_ids = response.json()[: limit * 4]  # on sur-échantillonne avant filtrage
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Hacker News injoignable : %s", exc)
            return []

        with ThreadPoolExecutor(max_workers=8) as pool:
            stories = [s for s in pool.map(self._fetch_story, story_ids) if s]

        relevant = [s for s in stories if self._is_relevant(s)]
        items = [self._to_item(s) for s in relevant][:limit]
        logger.info("[Hacker News] %s signal(aux) pertinent(s) sur %s stories", len(items), len(stories))
        return items

    def _fetch_story(self, story_id: int) -> dict | None:
        try:
            response = self._session.get(f"{_BASE}/item/{story_id}.json", timeout=self.timeout_s)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return None

    @staticmethod
    def _is_relevant(story: dict) -> bool:
        haystack = f"{story.get('title', '')} {story.get('url', '')}".lower()
        return any(term in haystack for term in _RELEVANT_TERMS)

    @staticmethod
    def _to_item(story: dict) -> TrendItem:
        story_id = story.get("id")
        published = story.get("time")
        return TrendItem(
            title=story.get("title", "").strip(),
            url=story.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
            source="Hacker News",
            origin=TrendOrigin.GLOBAL_TECH,
            summary=f"{story.get('descendants', 0)} commentaires",
            score=float(story.get("score", 0)),
            published_at=datetime.fromtimestamp(published, tz=UTC) if published else None,
        )
