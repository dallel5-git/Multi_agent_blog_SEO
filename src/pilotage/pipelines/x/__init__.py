"""Pipeline de contenu X — indépendant des cinq autres.

Statistiques : saisie manuelle (aucune API d'engagement gratuite, CADRAGE.md
risque n°4).
"""

from __future__ import annotations

from ...platforms import Platform
from ...shared.topic_selection import choose_topic_from_trends
from ..base import Draft, PlatformPipeline, Topic, TrendItem
from .watcher import collect_trends
from .writer import generate_post

_FALLBACK_TOPICS = (
    Topic(title="Le no-code n'est pas juste pour les non-tech", angle="Prise de position courte, argumentée."),
    Topic(title="n8n vs Make : mon avis après usage réel", angle="Retour d'expérience concis, sans jargon."),
    Topic(title="Une astuce n8n que peu de gens connaissent", angle="Tip concret, actionnable immédiatement."),
)


class XPipeline(PlatformPipeline):
    platform = Platform.X

    def watch(self) -> list[TrendItem]:
        return collect_trends(offline=self.offline)

    def choose_topic(self, trends: list[TrendItem]) -> Topic:
        return choose_topic_from_trends(
            trends, self.llm, content_kind="post X", fallback=_FALLBACK_TOPICS
        )

    def write(self, topic: Topic) -> Draft:
        return generate_post(topic, self.brand_kernel, self.llm)


__all__ = ["XPipeline"]
