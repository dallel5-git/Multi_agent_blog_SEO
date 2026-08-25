"""Rédaction du contenu du canal Telegram public.

⚠️ Ne pas confondre avec `TELEGRAM_BOT_TOKEN` (bot de validation du blog) ni
avec les 6 bots PRIVÉS de pilotage (`PILOTAGE_*_BOT_TOKEN`) : ce module
rédige le message posté sur `TELEGRAM_CHANNEL_USERNAME`, le canal PUBLIC —
la cible de publication, pas un outil (CADRAGE.md risque n°5).

Format retenu : un message direct, sans fioriture, en Markdown Telegram
simple (gras, listes), qui se termine par un lien ou une invitation claire.
"""

from __future__ import annotations

from ...brand_kernel.loader import render_prompt_block
from ...brand_kernel.schema import BrandKernel
from ...platforms import Platform
from ...shared.llm import LLMPort
from ..base import Draft, Topic

_FORMAT_INSTRUCTIONS = (
    "Tu rédiges un message pour un CANAL Telegram public : direct, sans "
    "fioriture, quelques phrases ou une courte liste. Formatage Markdown "
    "simple accepté par Telegram (*gras*, listes avec -). Termine par un "
    "lien ou une invitation claire (lire l'article, essayer l'outil)."
)


def generate_message(topic: Topic, kernel: BrandKernel, llm: LLMPort) -> Draft:
    system_prompt = (
        render_prompt_block(kernel, Platform.TELEGRAM_CHANNEL) + "\n\n" + _FORMAT_INSTRUCTIONS
    )
    user_prompt = (
        f"Sujet retenu : {topic.title}\n"
        f"Angle : {topic.angle}\n"
        + (f"Source : {topic.source_url}\n" if topic.source_url else "")
        + "Rédige le message du canal."
    )
    response = llm.generate(system_prompt, user_prompt, temperature=0.7)

    return Draft(title=topic.title, body=response.text, topic_summary=topic.angle)
