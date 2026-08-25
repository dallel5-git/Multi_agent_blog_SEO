"""Rédaction du contenu X.

Format retenu : un post court (280 caractères) si le sujet le permet, sinon
un thread de 3 à 5 tweets courts séparés par une ligne `---` — c'est au LLM
de juger, pas au pipeline d'imposer un format unique (CADRAGE.md, décision 9
laissait la question ouverte « thread ou post unique »). Bloc de marque en
variante COURTE (`short=True`).
"""

from __future__ import annotations

from ...brand_kernel.loader import render_prompt_block
from ...brand_kernel.schema import BrandKernel
from ...platforms import Platform
from ...shared.llm import LLMPort
from ..base import Draft, Topic

_FORMAT_INSTRUCTIONS = (
    "Tu rédiges un post X (Twitter) : un message court et percutant, 280 "
    "caractères maximum si un seul post suffit à couvrir le sujet. Si le "
    "sujet demande plus de place, structure plutôt un thread de 3 à 5 "
    "tweets courts, séparés par une ligne contenant uniquement '---' entre "
    "chaque tweet. Un ou deux hashtags maximum, seulement s'ils sont "
    "vraiment pertinents."
)


def generate_post(topic: Topic, kernel: BrandKernel, llm: LLMPort) -> Draft:
    system_prompt = render_prompt_block(kernel, Platform.X, short=True) + "\n\n" + _FORMAT_INSTRUCTIONS
    user_prompt = (
        f"Sujet retenu : {topic.title}\n"
        f"Angle : {topic.angle}\n"
        + (f"Source : {topic.source_url}\n" if topic.source_url else "")
        + "Rédige le post (ou le thread)."
    )
    response = llm.generate(system_prompt, user_prompt, temperature=0.75)

    return Draft(title=topic.title, body=response.text, topic_summary=topic.angle)
