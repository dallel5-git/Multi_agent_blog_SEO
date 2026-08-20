"""Source de veille : Reddit via les endpoints JSON publics (`.json`), sans clé ni OAuth.

Reddit exige un User-Agent explicite ; sans lui, l'API renvoie systématiquement 429.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import requests

from ...domain.entities.trend import TrendItem, TrendOrigin
from ...domain.ports.search import TechSourcePort

logger = logging.getLogger(__name__)


class RedditSource(TechSourcePort):
    """Posts chauds des subreddits configurés."""

    name = "Reddit"

    def __init__(
        self,
        subreddits: tuple[str, ...] | list[str],
        *,
        limit: int = 15,
        timeout_s: int = 20,
        user_agent: str = "blogseo/1.0",
        listing: str = "hot",
    ) -> None:
        self.subreddits = list(subreddits)
        self.limit = limit
        self.timeout_s = timeout_s
        self.listing = listing
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    def fetch(self, *, limit: int | None = None) -> list[TrendItem]:
        per_sub = max(3, (limit or self.limit) // max(1, len(self.subreddits)) + 2)
        items: list[TrendItem] = []
        for subreddit in self.subreddits:
            items.extend(self._fetch_subreddit(subreddit, per_sub))
            time.sleep(1.0)  # courtoisie : Reddit throttle vite les IP non authentifiées
        items.sort(key=lambda i: i.score, reverse=True)
        result = items[: (limit or self.limit)]
        logger.info("[Reddit] %s signal(aux) sur %s subreddit(s)", len(result), len(self.subreddits))
        return result

    def _fetch_subreddit(self, subreddit: str, limit: int) -> list[TrendItem]:
        url = f"https://www.reddit.com/r/{subreddit}/{self.listing}.json"
        try:
            response = self._session.get(url, params={"limit": limit, "t": "week"}, timeout=self.timeout_s)
            if response.status_code >= 400:
                logger.warning("Reddit r/%s → HTTP %s", subreddit, response.status_code)
                return []
            children = response.json().get("data", {}).get("children", [])
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Reddit r/%s injoignable : %s", subreddit, exc)
            return []

        items: list[TrendItem] = []
        for child in children:
            data = child.get("data", {})
            if data.get("stickied") or data.get("over_18"):
                continue
            created = data.get("created_utc")
            items.append(
                TrendItem(
                    title=(data.get("title") or "").strip(),
                    url=f"https://www.reddit.com{data.get('permalink', '')}",
                    source=f"r/{subreddit}",
                    origin=TrendOrigin.GLOBAL_TECH,
                    summary=(data.get("selftext") or "")[:300].replace("\n", " ").strip(),
                    score=float(data.get("ups", 0)),
                    published_at=datetime.fromtimestamp(created, tz=UTC) if created else None,
                )
            )
        return items
