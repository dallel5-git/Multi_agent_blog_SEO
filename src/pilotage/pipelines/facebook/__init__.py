"""Pipeline de contenu Facebook — indépendant des cinq autres.

Statistiques : Meta Graph API (automatique, même jeton de page qu'Instagram
— CADRAGE.md risque n°3).
"""

from __future__ import annotations

from ...platforms import Platform
from ...shared.topic_selection import choose_topic_from_trends
from ..base import Draft, PlatformPipeline, Topic, TrendItem
from .watcher import collect_trends
from .writer import generate_post

_FALLBACK_TOPICS = (
    Topic(
        title="Pourquoi automatiser sa prospection change tout pour une PME",
        angle="Ton accessible, exemples concrets, pas de jargon technique.",
    ),
    Topic(
        title="3 outils gratuits pour automatiser son business en Tunisie",
        angle="Liste pratique, ton chaleureux, appel à commenter avec son propre outil.",
    ),
    Topic(
        title="L'IA n'est pas réservée aux grandes entreprises",
        angle="Message rassurant, exemples locaux, invite à découvrir le blog.",
    ),
)


class FacebookPipeline(PlatformPipeline):
    platform = Platform.FACEBOOK

    def watch(self) -> list[TrendItem]:
        return collect_trends(offline=self.offline)

    def choose_topic(self, trends: list[TrendItem]) -> Topic:
        return choose_topic_from_trends(
            trends, self.llm, content_kind="post Facebook", fallback=_FALLBACK_TOPICS
        )

    def write(self, topic: Topic) -> Draft:
        return generate_post(topic, self.brand_kernel, self.llm)


__all__ = ["FacebookPipeline"]
