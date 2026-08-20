"""Value object `SeoMetadata` : les métadonnées optimisées par l'agent SEO Editor."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Bornes usuelles de Google pour l'affichage dans les SERP (en caractères).
TITLE_MIN, TITLE_MAX = 30, 60
DESCRIPTION_MIN, DESCRIPTION_MAX = 120, 158

_WORD_PATTERN = re.compile(r"\b[\wÀ-ÿ]+\b", re.UNICODE)


def contains_keyword(text: str, keyword: str) -> bool:
    """Vrai si tous les mots du mot-clé apparaissent dans `text`.

    On ne teste pas la sous-chaîne exacte : « prospection avec n8n » doit être
    considéré comme présent dans « Automatiser sa prospection commerciale avec
    n8n ». C'est ainsi que Google interprète une requête, et cela évite de
    forcer des titres artificiels.
    """
    if not keyword:
        return True
    haystack = text.lower()
    return all(word in haystack for word in _WORD_PATTERN.findall(keyword.lower()))


@dataclass(frozen=True, slots=True)
class SeoMetadata:
    """Métadonnées SEO d'un article, indépendantes du corps du texte."""

    meta_title: str
    meta_description: str
    focus_keyword: str
    secondary_keywords: tuple[str, ...] = ()
    internal_links: tuple[str, ...] = ()  # slugs d'articles existants à lier
    cover_alt_text: str = ""

    def title_issues(self) -> list[str]:
        """Écarts détectés sur le meta title (liste vide = conforme)."""
        issues: list[str] = []
        length = len(self.meta_title)
        if length < TITLE_MIN:
            issues.append(f"meta_title trop court ({length} < {TITLE_MIN})")
        if length > TITLE_MAX:
            issues.append(f"meta_title trop long ({length} > {TITLE_MAX})")
        if not contains_keyword(self.meta_title, self.focus_keyword):
            issues.append("meta_title ne contient pas le mot-clé principal")
        return issues

    def description_issues(self) -> list[str]:
        """Écarts détectés sur la meta description."""
        issues: list[str] = []
        length = len(self.meta_description)
        if length < DESCRIPTION_MIN:
            issues.append(f"meta_description trop courte ({length} < {DESCRIPTION_MIN})")
        if length > DESCRIPTION_MAX:
            issues.append(f"meta_description trop longue ({length} > {DESCRIPTION_MAX})")
        return issues

    def all_issues(self) -> list[str]:
        return self.title_issues() + self.description_issues()

    @property
    def is_valid(self) -> bool:
        return not self.all_issues()

    @property
    def all_keywords(self) -> tuple[str, ...]:
        return (self.focus_keyword, *self.secondary_keywords)
