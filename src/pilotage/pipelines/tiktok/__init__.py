"""Pipeline de contenu TikTok — indépendant des cinq autres.

Statistiques : saisie manuelle (aucune API d'engagement gratuite, CADRAGE.md
risque n°4).
"""

from __future__ import annotations

from ...platforms import Platform
from ...shared.topic_selection import choose_topic_from_trends
from ..base import Draft, PlatformPipeline, Topic, TrendItem
from .watcher import collect_trends
from .writer import generate_script

_FALLBACK_TOPICS = (
    Topic(
        title="3 automatisations n8n en 60 secondes",
        angle="Format rapide, une astuce concrète, immédiatement applicable.",
    ),
    Topic(
        title="L'IA peut faire ça pour toi (et c'est gratuit)",
        angle="Démonstration rapide d'un outil gratuit, sans jargon.",
    ),
    Topic(
        title="L'erreur n°1 quand on débute avec n8n",
        angle="Format punchy, un piège concret à éviter dès le premier workflow.",
    ),
)


class TikTokPipeline(PlatformPipeline):
    platform = Platform.TIKTOK

    def watch(self) -> list[TrendItem]:
        return collect_trends(offline=self.offline)

    def choose_topic(self, trends: list[TrendItem]) -> Topic:
        return choose_topic_from_trends(
            trends, self.llm, content_kind="short TikTok", fallback=_FALLBACK_TOPICS
        )

    def write(self, topic: Topic) -> Draft:
        return generate_script(topic, self.brand_kernel, self.llm)


__all__ = ["TikTokPipeline"]
