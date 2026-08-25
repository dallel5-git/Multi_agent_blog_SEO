"""Pipeline de contenu du canal Telegram public — indépendant des cinq autres.

Statistiques : Bot API (automatique — nombre d'abonnés au minimum).
"""

from __future__ import annotations

from ...platforms import Platform
from ...shared.topic_selection import choose_topic_from_trends
from ..base import Draft, PlatformPipeline, Topic, TrendItem
from .watcher import collect_trends
from .writer import generate_message

_FALLBACK_TOPICS = (
    Topic(
        title="Nouvel article : automatiser sa prospection avec n8n",
        angle="Message court, lien direct vers l'article du blog.",
    ),
    Topic(
        title="Le rappel de la semaine : une astuce n8n",
        angle="Format court et actionnable, ton direct.",
    ),
    Topic(
        title="Une ressource gratuite à connaître cette semaine",
        angle="Message simple, un lien, une raison d'y aller.",
    ),
)


class TelegramChannelPipeline(PlatformPipeline):
    platform = Platform.TELEGRAM_CHANNEL

    def watch(self) -> list[TrendItem]:
        return collect_trends(offline=self.offline)

    def choose_topic(self, trends: list[TrendItem]) -> Topic:
        return choose_topic_from_trends(
            trends, self.llm, content_kind="message de canal Telegram", fallback=_FALLBACK_TOPICS
        )

    def write(self, topic: Topic) -> Draft:
        return generate_message(topic, self.brand_kernel, self.llm)


__all__ = ["TelegramChannelPipeline"]
