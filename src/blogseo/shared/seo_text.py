"""Normalisation déterministe du meta_title / meta_description proposés par un LLM.

Le LLM propose ; ces fonctions corrigent (longueur, présence du mot-clé) pour
qu'aucune métadonnée non conforme ne sorte, que ce soit lors de la première
génération (`SeoEditorAgent`) ou d'un refresh ciblé (issue #42).
"""

from __future__ import annotations

from ..domain.value_objects.seo_metadata import DESCRIPTION_MAX, DESCRIPTION_MIN, TITLE_MAX, contains_keyword
from .text import truncate


def fix_meta_title(title: str, focus: str) -> str:
    """Garantit un meta title exploitable : mot-clé présent et longueur bornée.

    Priorité au sens : on ne remplace jamais un titre lisible par le seul
    mot-clé. Si le préfixage ne tient pas dans les `TITLE_MAX` caractères, on
    garde le titre d'origine tronqué.
    """
    title = title.strip().strip('"').rstrip(".")
    if not contains_keyword(title, focus):
        candidate = f"{focus.capitalize()} : {title}"
        if len(candidate) <= TITLE_MAX:
            return candidate
    return truncate(title, TITLE_MAX, suffix="")


def fix_meta_description(description: str, focus: str, body: str = "") -> str:
    """Complète ou tronque la description pour rester dans la fenêtre Google."""
    description = " ".join(description.split()).strip().strip('"')

    if len(description) < DESCRIPTION_MIN and body:
        # On complète avec le début du corps, nettoyé de son Markdown.
        filler = " ".join(
            line.strip("#* ") for line in body.splitlines()
            if line.strip() and not line.strip().startswith(("#", "`", "<", "-"))
        )
        description = (description + " " + filler).strip()

    if not contains_keyword(description, focus):
        description = f"{focus.capitalize()} : {description}"

    if len(description) > DESCRIPTION_MAX:
        description = truncate(description, DESCRIPTION_MAX, suffix="")
    return description.rstrip(" ,;:").rstrip(".") + "."
