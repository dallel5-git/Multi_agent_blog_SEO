"""Catégories autorisées par le blog Next.js (src/types/article.ts).

Toute valeur produite par les agents DOIT appartenir à cet ensemble, sinon le
build Next.js casse (le type TypeScript `Category` est une union fermée).
"""

from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    """Union fermée, miroir exact du type `Category` côté Next.js."""

    IA = "IA"
    N8N = "n8n"
    MAKE = "Make"
    PYTHON = "Python"
    AGENTS_IA = "Agents IA"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]

    @classmethod
    def coerce(cls, raw: str | None, default: Category = None) -> Category:
        """Convertit une chaîne libre produite par un LLM en catégorie valide.

        Le LLM renvoie parfois « n8N », « agents ia » ou « Automatisation ».
        On normalise, puis on retombe sur `default` (IA par défaut) si aucune
        correspondance n'est trouvée, plutôt que de laisser passer une valeur
        qui ferait échouer le build du blog.
        """
        fallback = default or cls.IA
        if not raw:
            return fallback

        normalized = raw.strip().lower().replace("-", " ").replace("_", " ")
        for member in cls:
            if member.value.lower() == normalized:
                return member

        # Correspondances approximatives fréquentes.
        aliases = {
            "agent ia": cls.AGENTS_IA,
            "agents": cls.AGENTS_IA,
            "ai agents": cls.AGENTS_IA,
            "intelligence artificielle": cls.IA,
            "ai": cls.IA,
            "llm": cls.IA,
            "automatisation": cls.N8N,
            "no code": cls.MAKE,
            "nocode": cls.MAKE,
            "integromat": cls.MAKE,
            "py": cls.PYTHON,
        }
        return aliases.get(normalized, fallback)
