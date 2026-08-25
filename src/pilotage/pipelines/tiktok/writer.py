"""Rédaction du contenu TikTok.

Format retenu : le script complet d'un short vertical (30-60 s), plus un
prompt de couverture réutilisable dérivé du Brand Kernel. Bloc de marque en
variante COURTE (`short=True`) : TikTok est un format bref au même titre
que X (voir `render_prompt_block`).
"""

from __future__ import annotations

from ...brand_kernel.loader import render_prompt_block
from ...brand_kernel.schema import BrandKernel
from ...platforms import Platform
from ...shared.llm import LLMPort
from ..base import Draft, Topic

_FORMAT_INSTRUCTIONS = (
    "Tu rédiges le SCRIPT COMPLET d'un short/vertical TikTok de 30 à 60 "
    "secondes : accroche dans les 2 premières secondes, un seul message "
    "clair, rythme rapide, phrase de fin qui donne envie de suivre le "
    "compte. Rédige du texte à dire à voix haute, pas des puces."
)


def generate_script(topic: Topic, kernel: BrandKernel, llm: LLMPort) -> Draft:
    system_prompt = render_prompt_block(kernel, Platform.TIKTOK, short=True) + "\n\n" + _FORMAT_INSTRUCTIONS
    user_prompt = (
        f"Sujet retenu : {topic.title}\n"
        f"Angle : {topic.angle}\n"
        + (f"Source : {topic.source_url}\n" if topic.source_url else "")
        + "Rédige le script complet du short."
    )
    response = llm.generate(system_prompt, user_prompt, temperature=0.8)

    image_prompt = (
        f"Couverture verticale TikTok pour un short intitulé « {topic.title} ». "
        f"{kernel.visual.thumbnail_style} Format 9:16, texte très court et lisible."
    )

    return Draft(
        title=topic.title,
        body=response.text,
        image_prompt=image_prompt,
        topic_summary=topic.angle,
    )
