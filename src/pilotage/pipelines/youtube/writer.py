"""Rédaction du contenu YouTube.

Format retenu par l'auteur : le SCRIPT COMPLET de la vidéo (pas un simple
plan), plus un prompt de miniature réutilisable dérivé du Brand Kernel — le
même prompt redonné à un générateur d'image garde le même thème visuel d'une
vidéo à l'autre.
"""

from __future__ import annotations

from ...brand_kernel.loader import render_prompt_block
from ...brand_kernel.schema import BrandKernel
from ...platforms import Platform
from ...shared.llm import LLMPort
from ..base import Draft, Topic

_FORMAT_INSTRUCTIONS = (
    "Tu rédiges le SCRIPT COMPLET d'une vidéo YouTube, pas un simple plan : "
    "une accroche (hook) dans les 10 premières secondes, des sections "
    "structurées avec des transitions parlées et des exemples concrets, puis "
    "un appel à l'action de fin (abonnement + mention du prochain contenu). "
    "Rédige du texte à dire à voix haute, pas des puces télégraphiques."
)


def generate_script(topic: Topic, kernel: BrandKernel, llm: LLMPort) -> Draft:
    system_prompt = render_prompt_block(kernel, Platform.YOUTUBE) + "\n\n" + _FORMAT_INSTRUCTIONS
    user_prompt = (
        f"Sujet retenu : {topic.title}\n"
        f"Angle : {topic.angle}\n"
        + (f"Source : {topic.source_url}\n" if topic.source_url else "")
        + "Rédige le script complet de la vidéo."
    )
    response = llm.generate(system_prompt, user_prompt, temperature=0.75)

    image_prompt = (
        f"Miniature YouTube pour une vidéo intitulée « {topic.title} ». "
        f"{kernel.visual.thumbnail_style} Composition centrée sur le sujet, "
        "texte court et lisible en gros caractères, un seul point focal."
    )

    return Draft(
        title=topic.title,
        body=response.text,
        image_prompt=image_prompt,
        topic_summary=topic.angle,
    )
