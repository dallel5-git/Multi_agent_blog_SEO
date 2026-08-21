"""Rendu texte de la section « Cette série » (issue #41), sans I/O.

Fonctions pures partagées entre `PublisherAgent` (application) et
`SeriesBacklinkWriter` (infrastructure) : la section vit dans un bloc borné
par des marqueurs HTML, remplacé de façon idempotente plutôt qu'ajouté en
aveugle — contrairement au « À lire aussi » du SEO Editor, elle doit pouvoir
être réécrite à chaque nouvelle publication de la série, y compris dans des
articles déjà publiés.
"""

from __future__ import annotations

import re

_START = "<!-- series:start -->"
_END = "<!-- series:end -->"
_BLOCK_PATTERN = re.compile(re.escape(_START) + r".*?" + re.escape(_END), re.DOTALL)


def render_series_section(entries: list[tuple[str, str]]) -> str:
    """`entries` = [(slug, titre), ...] dans l'ordre de publication de la série."""
    lines = [f"- [{title}](/blog/{slug})" for slug, title in entries]
    return f"{_START}\n## Cette série\n\n" + "\n".join(lines) + f"\n{_END}"


def upsert_series_section(mdx_body: str, entries: list[tuple[str, str]]) -> str:
    """Insère ou remplace la section série dans le corps Markdown d'un article.

    Idempotent : rejouer avec la même liste d'entrées ne duplique rien.
    N'interfère pas avec un « ## À lire aussi » déjà présent (marqueurs
    distincts).
    """
    if not entries:
        return mdx_body

    block = render_series_section(entries)
    if _BLOCK_PATTERN.search(mdx_body):
        return _BLOCK_PATTERN.sub(block, mdx_body)
    return mdx_body.rstrip() + "\n\n" + block + "\n"
