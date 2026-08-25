"""Pont EN LECTURE SEULE : articles publiés du blog → `content_items`.

Le blog compte comme septième entrée du calendrier (`platform = 'blog'`),
afin que les six pipelines puissent proposer une mention croisée vers un
article. Ce module lit les `.mdx` de `content/articles/` et leur frontmatter
exactement comme le ferait un outil externe — **jamais d'import de
`blogseo`**, jamais d'écriture dans le dossier du blog.

Le frontmatter est parsé avec PyYAML (dépendance déjà déclarée du projet),
sur le même principe que `blogseo.infrastructure.persistence.mdx_article_source`
— dont ce module s'inspire sans l'importer, la règle d'isolation l'interdit.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml

from ..platforms import Platform
from .models import ContentItem, ContentStatus, PlatformPost
from .repository import CalendarRepository

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(raw: str) -> dict:
    match = _FRONTMATTER_PATTERN.match(raw)
    if not match:
        return {}
    parsed = yaml.safe_load(match.group(1))
    return parsed if isinstance(parsed, dict) else {}


def _article_url(blog_base_url: str, slug: str) -> str:
    """`mon-article.mdx` → `{blog_base_url}/blog/mon-article` (MEMOIRE.md §4)."""
    return f"{blog_base_url.rstrip('/')}/blog/{slug}"


def sync_blog_articles(
    repository: CalendarRepository,
    content_dir: Path,
    blog_base_url: str,
) -> int:
    """Insère les articles publiés absents du calendrier. Idempotent : relancer
    ne duplique rien, `find_post_by_url` sert de clé d'idempotence."""
    if not content_dir.exists():
        return 0

    inserted = 0
    for path in sorted(content_dir.glob("*.mdx")):
        slug = path.stem
        url = _article_url(blog_base_url, slug)
        if repository.find_post_by_url(url) is not None:
            continue

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue

        front = _parse_frontmatter(raw)
        title = str(front.get("title") or slug)
        description = str(front.get("description") or "")
        published_at = str(front.get("date") or "") or date.fromtimestamp(
            path.stat().st_mtime
        ).isoformat()

        item_id = repository.add_item(
            ContentItem(
                platform=Platform.BLOG,
                title=title,
                topic=description or None,
                status=ContentStatus.PUBLISHED,
                scheduled_for=published_at,
            )
        )
        repository.add_post(
            PlatformPost(
                content_item_id=item_id,
                platform=Platform.BLOG,
                url=url,
                external_id=slug,
                published_at=published_at,
            )
        )
        inserted += 1

    return inserted
