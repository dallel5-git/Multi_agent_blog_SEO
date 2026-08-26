"""Adaptateur du `ArticleRefreshPort` : relit/réécrit le titre et la description
d'un article déjà publié, sans jamais toucher au corps ni au nom de fichier
(issue #42 — régénération des articles sous-performants).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ...domain.errors import PublicationError
from ...domain.ports.publishing import ArticleRefreshPort, ExistingArticle
from ...shared.atomic_write import atomic_write_text
from ...shared.text import quote_yaml_scalar
from ..persistence.mdx_article_source import parse_frontmatter

logger = logging.getLogger(__name__)

_FRONTMATTER_BLOCK = re.compile(r"^(---\s*\n)(.*?\n)(---\s*\n)", re.DOTALL)


def _replace_scalar_line(block: str, key: str, value: str) -> str:
    """Remplace la ligne `key: ...` du frontmatter par une nouvelle valeur.

    Le frontmatter est toujours produit par `Article.to_frontmatter()`, donc
    la clé existe forcément ; un article sans cette clé est un fichier
    corrompu qui doit faire échouer le refresh plutôt qu'être réparé en silence.
    """
    pattern = re.compile(rf"(?m)^{re.escape(key)}:.*$")
    if not pattern.search(block):
        raise PublicationError(f"Champ « {key} » introuvable dans le frontmatter")
    return pattern.sub(f"{key}: {quote_yaml_scalar(value)}", block, count=1)


class MdxArticleRefresher(ArticleRefreshPort):
    """Relit et réécrit uniquement `title`/`description` d'un `.mdx` publié."""

    def __init__(self, blog_content_dir: Path) -> None:
        self.blog_content_dir = blog_content_dir

    def read(self, slug: str) -> ExistingArticle | None:
        path = self.blog_content_dir / f"{slug}.mdx"
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        front = parse_frontmatter(raw)
        match = _FRONTMATTER_BLOCK.match(raw)
        body = raw[match.end():] if match else raw
        return ExistingArticle(
            slug=slug,
            title=str(front.get("title", slug)),
            description=str(front.get("description", "")),
            category=str(front.get("category", "")),
            body_markdown=body.strip(),
        )

    def update_metadata(self, slug: str, *, title: str, description: str) -> Path | None:
        path = self.blog_content_dir / f"{slug}.mdx"
        if not path.exists():
            return None

        raw = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_BLOCK.match(raw)
        if not match:
            raise PublicationError(f"Frontmatter introuvable dans {path}")

        block = match.group(2)
        block = _replace_scalar_line(block, "title", title)
        block = _replace_scalar_line(block, "description", description)
        updated = raw[: match.start(2)] + block + raw[match.end(2):]

        try:
            atomic_write_text(path, updated)
        except OSError as exc:
            raise PublicationError(f"Écriture impossible de {path} : {exc}") from exc

        logger.info("Métadonnées mises à jour en place : %s", path)
        return path
