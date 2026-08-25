"""Pipeline de contenu YouTube — indépendant des cinq autres.

Statistiques : Data API v3 (quota gratuit 10 000 unités/jour).

C'est le pipeline PILOTE (CADRAGE.md, lot 3) : validé de bout en bout avant
duplication sur les cinq autres plateformes.
"""

from __future__ import annotations

import json
import re

from ...platforms import Platform
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


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class YouTubePipeline(PlatformPipeline):
    """Pipeline pilote : veille (HN/Reddit/dev.to/RSS Tunisie) → sujet → script."""

    platform = Platform.YOUTUBE

    def watch(self) -> list[TrendItem]:
        return collect_trends(offline=self.offline)

    def choose_topic(self, trends: list[TrendItem]) -> Topic:
        if not trends:
            return _FALLBACK_TOPICS[0]

        best = max(trends, key=lambda item: item.score)
        response = self.llm.generate(
            "Tu choisis un sujet de vidéo YouTube pertinent pour une niche IA / "
            "automatisation / productivité, et tu ne renvoies QUE du JSON.",
            (
                f"Signal retenu : {best.title} ({best.source})\n"
                f"Résumé : {best.summary}\n\n"
                "Renvoie un JSON avec les clés 'title' (titre accrocheur, en français, "
                "pour une vidéo YouTube) et 'angle' (une phrase sur l'angle pratique/"
                "tunisien à adopter)."
            ),
            json_mode=True,
        )
        payload = _extract_json(response.text)
        title = str(payload.get("title") or best.title)
        angle = str(payload.get("angle") or "Angle pratique, exemples concrets.")
        return Topic(title=title, angle=angle, source_url=best.url)

    def write(self, topic: Topic) -> Draft:
        return generate_script(topic, self.brand_kernel, self.llm)


__all__ = ["YouTubePipeline"]
