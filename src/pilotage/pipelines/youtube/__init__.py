"""Pipeline de contenu YouTube — indépendant des cinq autres.

Statistiques : Data API v3 (quota gratuit 10 000 unités/jour).

C'est le pipeline PILOTE (CADRAGE.md, lot 3) : validé de bout en bout avant
duplication sur les cinq autres plateformes.
"""

from __future__ import annotations

from ...platforms import Platform
from ...shared.topic_selection import choose_topic_from_trends
from ..base import Draft, PlatformPipeline, Topic, TrendItem
from .watcher import collect_trends
from .writer import generate_script

#: Sujets de repli si toutes les sources de veille sont mortes ou vides —
#: `choose_topic()` doit fonctionner même sans aucun signal (CADRAGE.md,
#: critère d'acceptation « aucune source morte ne fait échouer le run »).
_FALLBACK_TOPICS = (
    Topic(
        title="5 automatisations n8n à connaître en 2026",
        angle="Sélection commentée, sans jargon, exemples concrets pour PME tunisiennes.",
    ),
    Topic(
        title="IA générative : ce qui change vraiment pour les PME tunisiennes",
        angle="Panorama concret, cas d'usage locaux, sans survendre la technologie.",
    ),
    Topic(
        title="Construire son premier agent IA autonome",
        angle="Tutoriel pas à pas, outils gratuits, résultat utilisable en fin de vidéo.",
    ),
)


class YouTubePipeline(PlatformPipeline):
    """Pipeline pilote : veille (HN/Reddit/dev.to/RSS Tunisie) → sujet → script."""

    platform = Platform.YOUTUBE

    def watch(self) -> list[TrendItem]:
        return collect_trends(offline=self.offline)

    def choose_topic(self, trends: list[TrendItem]) -> Topic:
        return choose_topic_from_trends(
            trends, self.llm, content_kind="vidéo YouTube", fallback=_FALLBACK_TOPICS
        )

    def write(self, topic: Topic) -> Draft:
        return generate_script(topic, self.brand_kernel, self.llm)


__all__ = ["YouTubePipeline"]
