"""Rédaction du contenu Instagram.

Format retenu par l'auteur : un CAROUSEL — l'auteur a son propre template
visuel Instagram, le rédacteur ne fournit donc que le contenu de chaque page
(`Draft.carousel_pages`) plutôt qu'un visuel déjà composé. `image_prompt`
porte un seul prompt de fond, réutilisé sur toutes les pages pour garder le
même thème visuel d'une publication à l'autre.
"""

from __future__ import annotations

from ...brand_kernel.loader import render_prompt_block
from ...brand_kernel.schema import BrandKernel
from ...platforms import Platform
from ...shared.json_utils import extract_json
from ...shared.llm import LLMPort
from ..base import Draft, Topic

_FORMAT_INSTRUCTIONS = (
    "Tu prépares un CAROUSEL Instagram : renvoie un JSON strict avec deux "
    "clés — 'caption' (légende d'accompagnement du post, avec un appel à "
    "l'action) et 'pages' (liste de 5 à 7 chaînes de texte courtes, une par "
    "page du carousel, qui se lisent dans l'ordre comme un mini-tutoriel). "
    "Chaque page doit être courte : elle sera posée telle quelle sur un "
    "template visuel déjà conçu par l'auteur, pas de mise en forme, juste "
    "le texte de la page."
)

_DEFAULT_PAGES = ("Introduction du sujet.", "Point clé à retenir.")


def generate_carousel(topic: Topic, kernel: BrandKernel, llm: LLMPort) -> Draft:
    system_prompt = render_prompt_block(kernel, Platform.INSTAGRAM) + "\n\n" + _FORMAT_INSTRUCTIONS
    user_prompt = (
        f"Sujet retenu : {topic.title}\n"
        f"Angle : {topic.angle}\n"
        + (f"Source : {topic.source_url}\n" if topic.source_url else "")
        + "Renvoie le JSON du carousel."
    )
    response = llm.generate(system_prompt, user_prompt, temperature=0.75, json_mode=True)
    payload = extract_json(response.text)

    pages_bruts = payload.get("pages")
    pages = (
        tuple(str(page) for page in pages_bruts)
        if isinstance(pages_bruts, list) and pages_bruts
        else _DEFAULT_PAGES
    )
    caption = str(payload.get("caption") or topic.angle)

    image_prompt = (
        f"Template de fond pour un carousel Instagram sur « {topic.title} ». "
        f"{kernel.visual.thumbnail_style} Même fond réutilisé sur les {len(pages)} pages "
        "pour une identité visuelle cohérente ; laisser l'espace pour le texte de chaque page."
    )

    return Draft(
        title=topic.title,
        body=caption,
        image_prompt=image_prompt,
        carousel_pages=pages,
        topic_summary=topic.angle,
    )
