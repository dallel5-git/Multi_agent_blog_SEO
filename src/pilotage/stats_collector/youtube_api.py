"""Collecteur YouTube — Data API v3, REST brut (`requests`), pas de SDK Google.

`videos.list(part=statistics)` renvoie des COMPTEURS CUMULÉS (total de vues
depuis toujours), pas un delta depuis `since` : ce paramètre existe pour
respecter le port `StatsCollector`, mais cette API ne permet pas de le
filtrer — chaque appel redonne un instantané complet, ce qui est exactement
le principe d'accumulation de `stat_snapshots` (voir schema.sql).

Quota gratuit : 10 000 unités/jour, 1 unité par appel `videos.list` (jusqu'à
50 ids par appel) — une collecte quotidienne de toutes les vidéos publiées
ne s'approche jamais de la limite.
"""

from __future__ import annotations

from datetime import date

import requests

from ..platforms import Platform
from ..shared_calendar.models import PlatformPost, StatSnapshot, StatSource
from ..shared_calendar.repository import CalendarRepository
from .base import StatsCollector

_TIMEOUT_S = 20
_VIDEOS_ENDPOINT = "https://www.googleapis.com/youtube/v3/videos"
#: L'API accepte jusqu'à 50 ids séparés par des virgules en un seul appel.
_MAX_IDS_PER_CALL = 50


class YouTubeStatsCollector(StatsCollector):
    platform = Platform.YOUTUBE

    def __init__(self, repository: CalendarRepository, *, api_key: str) -> None:
        super().__init__(repository)
        self.api_key = api_key

    def collect(self, since: date) -> list[StatSnapshot]:
        if not self.api_key:
            self.logger.info("YOUTUBE_API_KEY absente — collecte ignorée.")
            return []

        posts = [
            post for post in self.repository.list_recent_posts(limit=200)
            if post.platform is Platform.YOUTUBE and post.external_id
        ]
        if not posts:
            return []

        by_video_id = {post.external_id: post for post in posts}
        snapshots: list[StatSnapshot] = []

        video_ids = list(by_video_id)
        for debut in range(0, len(video_ids), _MAX_IDS_PER_CALL):
            lot = video_ids[debut : debut + _MAX_IDS_PER_CALL]
            snapshots.extend(self._collect_batch(lot, by_video_id))

        return snapshots

    def _collect_batch(
        self, video_ids: list[str], by_video_id: dict[str, PlatformPost]
    ) -> list[StatSnapshot]:
        try:
            response = requests.get(
                _VIDEOS_ENDPOINT,
                params={"part": "statistics", "id": ",".join(video_ids), "key": self.api_key},
                timeout=_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            self.logger.warning("YouTube Data API injoignable : %s", exc)
            return []

        if response.status_code == 403:
            self.logger.warning(
                "YouTube Data API → HTTP 403 (quota probablement épuisé) : collecte ignorée cette fois."
            )
            return []
        if response.status_code >= 400:
            self.logger.warning("YouTube Data API → HTTP %s", response.status_code)
            return []

        try:
            items = response.json().get("items", [])
        except ValueError:
            self.logger.warning("Réponse YouTube Data API non JSON.")
            return []

        snapshots = []
        for item in items:
            post = by_video_id.get(item.get("id"))
            if post is None:
                continue
            stats = item.get("statistics", {})
            snapshots.append(
                StatSnapshot(
                    platform=Platform.YOUTUBE,
                    platform_post_id=post.id,
                    source=StatSource.API,
                    views=int(stats.get("viewCount", 0)),
                    likes=int(stats.get("likeCount", 0)),
                    comments=int(stats.get("commentCount", 0)),
                )
            )
        return snapshots
