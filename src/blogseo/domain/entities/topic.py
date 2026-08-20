"""Entité `Topic` : le sujet retenu par le Keyword Analyst avant rédaction."""

from __future__ import annotations

from dataclasses import dataclass

from ..value_objects.category import Category


@dataclass(frozen=True, slots=True)
class Keyword:
    """Mot-clé SEO avec son intention de recherche estimée."""

    term: str
    intent: str = "informational"  # informational | tutorial | comparison | transactional
    priority: int = 1              # 1 = principal, 2+ = secondaire

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.term


@dataclass(slots=True)
class Topic:
    """Sujet d'article validé : angle, mots-clés, sources et preuve d'originalité."""

    title: str
    angle: str                       # angle tunisien explicite exigé par la ligne éditoriale
    category: Category
    primary_keyword: Keyword
    secondary_keywords: tuple[Keyword, ...] = ()
    rationale: str = ""              # pourquoi ce sujet maintenant
    target_audience: str = "Étudiants, PME et développeurs tunisiens"
    sources: tuple[str, ...] = ()
    # Renseigné par le détecteur de doublons (0.0 = totalement neuf).
    similarity_score: float = 0.0
    similar_slug: str | None = None
    outline: tuple[str, ...] = ()    # plan H2 proposé

    @property
    def all_keyword_terms(self) -> tuple[str, ...]:
        return (self.primary_keyword.term, *(k.term for k in self.secondary_keywords))

    def is_duplicate(self, threshold: float) -> bool:
        """Vrai si le sujet est sémantiquement trop proche d'un article existant."""
        return self.similarity_score >= threshold

    def as_brief(self) -> str:
        """Brief compact passé au Content Writer."""
        outline = "\n".join(f"  {i + 1}. {h}" for i, h in enumerate(self.outline)) or "  (libre)"
        secondary = ", ".join(k.term for k in self.secondary_keywords) or "(aucun)"
        return (
            f"TITRE DE TRAVAIL : {self.title}\n"
            f"CATÉGORIE : {self.category.value}\n"
            f"ANGLE TUNISIEN : {self.angle}\n"
            f"AUDIENCE : {self.target_audience}\n"
            f"MOT-CLÉ PRINCIPAL : {self.primary_keyword.term} "
            f"(intention : {self.primary_keyword.intent})\n"
            f"MOTS-CLÉS SECONDAIRES : {secondary}\n"
            f"POURQUOI CE SUJET : {self.rationale}\n"
            f"PLAN PROPOSÉ :\n{outline}\n"
            f"SOURCES : {', '.join(self.sources) or '(aucune)'}"
        )
