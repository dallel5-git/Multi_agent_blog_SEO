"""Sélection de sujet, partagée par les 6 pipelines.

Prend le signal de veille le plus fort, demande au LLM un titre et un angle
adaptés au format de la plateforme (`content_kind`, ex. « vidéo YouTube »,
« post X »), et retombe sur une liste de sujets de repli déterministe si
`trends` est vide — aucune source morte ne doit empêcher `choose_topic()` de
renvoyer un sujet exploitable.
"""

from __future__ import annotations

from ..pipelines.base import Topic, TrendItem
from .json_utils import extract_json
from .llm import LLMPort


def choose_topic_from_trends(
    trends: list[TrendItem],
    llm: LLMPort,
    *,
    content_kind: str,
    fallback: tuple[Topic, ...],
) -> Topic:
    if not trends:
        return fallback[0]

    best = max(trends, key=lambda item: item.score)
    response = llm.generate(
        f"Tu choisis un sujet de {content_kind} pertinent pour une niche IA / "
        "automatisation / productivité, et tu ne renvoies QUE du JSON.",
        (
            f"Signal retenu : {best.title} ({best.source})\n"
            f"Résumé : {best.summary}\n\n"
            "Renvoie un JSON avec les clés 'title' (titre accrocheur, en français) "
            "et 'angle' (une phrase sur l'angle pratique/tunisien à adopter)."
        ),
        json_mode=True,
    )
    payload = extract_json(response.text)
    title = str(payload.get("title") or best.title)
    angle = str(payload.get("angle") or "Angle pratique, exemples concrets.")
    return Topic(title=title, angle=angle, source_url=best.url)
