"""Entité `Article` : le livrable central du pipeline.

L'entité connaît le format attendu par le blog Next.js (frontmatter YAML + MDX)
mais ignore totalement *où* et *comment* le fichier sera écrit : c'est le rôle
des adapters de la couche infrastructure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date

from ...shared.text import quote_yaml_scalar as _yaml_quote
from ..value_objects.category import Category
from ..value_objects.seo_metadata import SeoMetadata
from ..value_objects.slug import Slug

# Le blog rend le MDX : les guillemets doubles dans le frontmatter doivent être échappés.
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_CODE_FENCE_PATTERN = re.compile(r"^```[\w-]*\s*$", re.MULTILINE)


@dataclass(slots=True)
class Article:
    """Article de blog complet, prêt à être écrit en `.mdx`."""

    title: str
    slug: Slug
    body_markdown: str
    seo: SeoMetadata
    category: Category = Category.IA
    tags: tuple[str, ...] = ()
    published_on: date = field(default_factory=date.today)
    author: str = "Oussama Dallel"
    cover_image: str = ""
    youtube_url: str = ""
    featured: bool = False
    # Traçabilité : d'où vient le sujet, quelles sources ont été utilisées.
    sources: tuple[str, ...] = ()
    revision: int = 1

    # ------------------------------------------------------------------ #
    # Mesures utilisées par le Quality Gate
    # ------------------------------------------------------------------ #
    @property
    def word_count(self) -> int:
        """Nombre de mots du corps, hors blocs de code (le code n'est pas du contenu SEO)."""
        without_code = re.sub(r"```.*?```", " ", self.body_markdown, flags=re.DOTALL)
        return len(re.findall(r"\b[\wÀ-ÿ'-]+\b", without_code))

    @property
    def headings(self) -> list[tuple[int, str]]:
        """Liste des titres sous la forme (niveau, texte).

        Les blocs de code sont neutralisés au préalable : sans cela, un simple
        commentaire Python `# ...` serait pris pour un titre H1 et déclencherait
        à tort un blocage du Quality Gate.
        """
        without_code = re.sub(r"```.*?```", "\n", self.body_markdown, flags=re.DOTALL)
        return [(len(m.group(1)), m.group(2).strip()) for m in _HEADING_PATTERN.finditer(without_code)]

    @property
    def h2_count(self) -> int:
        return sum(1 for level, _ in self.headings if level == 2)

    @property
    def has_balanced_code_fences(self) -> bool:
        """Un nombre impair de ``` casse le rendu MDX de la page."""
        return len(_CODE_FENCE_PATTERN.findall(self.body_markdown)) % 2 == 0

    def keyword_density(self, keyword: str) -> float:
        """Densité d'un mot-clé dans le corps (0.0 à 1.0)."""
        if not keyword or self.word_count == 0:
            return 0.0
        occurrences = len(re.findall(re.escape(keyword.lower()), self.body_markdown.lower()))
        return occurrences / self.word_count

    # ------------------------------------------------------------------ #
    # Sérialisation vers le format du blog
    # ------------------------------------------------------------------ #
    def to_frontmatter(self) -> str:
        """Frontmatter YAML strictement aligné sur `ArticleFrontmatter` (Next.js)."""
        tags_yaml = "[" + ", ".join(_yaml_quote(t) for t in self.tags) + "]"
        lines = [
            "---",
            f"title: {_yaml_quote(self.seo.meta_title or self.title)}",
            f"description: {_yaml_quote(self.seo.meta_description)}",
            f'date: "{self.published_on.isoformat()}"',
            f"category: {_yaml_quote(self.category.value)}",
            f"tags: {tags_yaml}",
            f"coverImage: {_yaml_quote(self.cover_image)}",
            f"youtubeUrl: {_yaml_quote(self.youtube_url)}",
            f"author: {_yaml_quote(self.author)}",
            f"featured: {'true' if self.featured else 'false'}",
            "---",
        ]
        return "\n".join(lines)

    def to_mdx(self) -> str:
        """Document `.mdx` complet, tel qu'il sera écrit dans content/articles/."""
        return f"{self.to_frontmatter()}\n\n{self.body_markdown.strip()}\n"

    def with_body(self, body_markdown: str) -> Article:
        """Copie de l'article avec un nouveau corps (incrémente la révision)."""
        return replace(self, body_markdown=body_markdown, revision=self.revision + 1)

    def with_seo(self, seo: SeoMetadata) -> Article:
        return replace(self, seo=seo)
