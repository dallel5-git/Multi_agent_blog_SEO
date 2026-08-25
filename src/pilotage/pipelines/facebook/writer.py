"""Rédaction du contenu Facebook.

Format retenu : un post texte de quelques phrases (plus long qu'un post X),
avec un appel à l'action clair, accompagné d'un prompt de visuel réutilisable
dérivé du Brand Kernel.
"""

from __future__ import annotations

from ...brand_kernel.loader import render_prompt_block
from ...brand_kernel.schema import BrandKernel
from ...platforms import Platform
from ...shared.llm import LLMPort
from ..base import Draft, Topic

_FORMAT_INSTRUCTIONS = (
    "Tu rédiges un post Facebook : quelques phrases engageantes, ton "
    "conversationnel, jusqu'à quelques courts paragraphes si le sujet le "
    "justifie. Termine par un appel à l'action clair (commenter, aller lire "
    "l'article du blog, essayer l'outil, etc.)."
)


def generate_post(topic: Topic, kernel: BrandKernel, llm: LLMPort) -> Draft:
    system_prompt = render_prompt_block(kernel, Platform.FACEBOOK) + "\n\n" + _FORMAT_INSTRUCTIONS
    user_prompt = (
        f"Sujet retenu : {topic.title}\n"
        f"Angle : {topic.angle}\n"
        + (f"Source : {topic.source_url}\n" if topic.source_url else "")
        + "Rédige le post."
    )
    response = llm.generate(system_prompt, user_prompt, temperature=0.75)

    image_prompt = f"Visuel Facebook pour un post sur « {topic.title} ». {kernel.visual.thumbnail_style}"

    return Draft(
        title=topic.title,
        body=response.text,
        image_prompt=image_prompt,
        topic_summary=topic.angle,
    )
