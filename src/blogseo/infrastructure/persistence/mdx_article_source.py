"""Lecture des articles `.mdx` déjà publiés dans le blog Next.js.

Le frontmatter est parsé « à la main » (petit sous-ensemble YAML : scalaires,
booléens, listes inline) pour éviter d'imposer PyYAML. Si PyYAML est présent,
on l'utilise car il est plus robuste.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ...domain.ports.repositories import ArticleSourcePort, PublishedArticleRef

logger = logging.getLogger(__name__)

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(raw: str) -> dict:
    """Extrait le frontmatter YAML d'un fichier `.mdx`. Renvoie {} s'il n'y en a pas."""
    match = _FRONTMATTER_PATTERN.match(raw)
    if not match:
        return {}
    block = match.group(1)

    try:  # chemin privilégié : PyYAML si disponible
        import yaml  # type: ignore[import-not-found]

        parsed = yaml.safe_load(block)
        return parsed if isinstance(parsed, dict) else {}
    except ImportError:
        pass

    return _parse_simple_yaml(block)


def _parse_simple_yaml(block: str) -> dict:
    """Parseur minimal : `clé: valeur`, listes inline `[a, b]`, booléens."""
    data: dict = {}
    for line in block.splitlines():
        line = line.rstrip()
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [item.strip().strip("\"'") for item in inner.split(",") if item.strip()] if inner else []
            continue
        if value.lower() in {"true", "false"}:
            data[key] = value.lower() == "true"
            continue
        data[key] = value.strip("\"'")
    return data


class MdxArticleSource(ArticleSourcePort):
    """Lit `content/articles/*.mdx` et en extrait les références d'articles."""

    def __init__(self, articles_dir: Path) -> None:
        self.articles_dir = articles_dir

    def list_published(self) -> list[PublishedArticleRef]:
        if not self.articles_dir.exists():
            logger.warning("Dossier d'articles introuvable : %s", self.articles_dir)
            return []

        refs: list[PublishedArticleRef] = []
        for path in sorted(self.articles_dir.glob("*.mdx")):
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Lecture impossible de %s : %s", path.name, exc)
                continue

            front = parse_frontmatter(raw)
            tags = front.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            refs.append(
                PublishedArticleRef(
                    slug=path.stem,
                    title=str(front.get("title", path.stem)),
                    description=str(front.get("description", "")),
                    category=str(front.get("category", "")),
                    date=str(front.get("date", "")),
                    tags=tuple(str(t) for t in tags),
                )
            )

        logger.info("%s article(s) existant(s) détecté(s) dans %s", len(refs), self.articles_dir)
        return refs

    def slugs(self) -> set[str]:
        if not self.articles_dir.exists():
            return set()
        return {path.stem for path in self.articles_dir.glob("*.mdx")}
