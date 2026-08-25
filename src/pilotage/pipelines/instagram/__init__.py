"""Pipeline de contenu Instagram — indépendant des cinq autres.

Statistiques : Meta Graph API (automatique, une fois le compte Instagram
Business relié — CADRAGE.md risque n°3).
"""

from __future__ import annotations

from ...platforms import Platform
from ...shared.topic_selection import choose_topic_from_trends
from ..base import Draft, PlatformPipeline, Topic, TrendItem
from .watcher import collect_trends
from .writer import generate_carousel

_FALLBACK_TOPICS = (
    Topic(
        title="5 automatisations n8n à connaître",
        angle="Carousel pédagogique, une automatisation par page, exemples concrets.",
    ),
    Topic(
        title="Comment choisir entre n8n et Make",
        angle="Comparatif visuel simple, critères pratiques pour PME tunisiennes.",
    ),
    Topic(
        title="Ton premier agent IA en 5 étapes",
        angle="Mini-tutoriel visuel, une étape par page, résultat concret à la fin.",
    ),
)


class InstagramPipeline(PlatformPipeline):
    platform = Platform.INSTAGRAM

    def watch(self) -> list[TrendItem]:
        return collect_trends(offline=self.offline)

    def choose_topic(self, trends: list[TrendItem]) -> Topic:
        return choose_topic_from_trends(
            trends, self.llm, content_kind="carousel Instagram", fallback=_FALLBACK_TOPICS
        )

    def write(self, topic: Topic) -> Draft:
        return generate_carousel(topic, self.brand_kernel, self.llm)


__all__ = ["InstagramPipeline"]
