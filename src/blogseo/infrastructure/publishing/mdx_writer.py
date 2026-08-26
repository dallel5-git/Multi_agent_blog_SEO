"""Écriture d'un `Article` au format `.mdx` attendu par le blog Next.js.

Deux destinations possibles :
- `storage/drafts/` : brouillon systématique, écrit à chaque run (même en dry-run) ;
- `content/articles/` : le vrai dossier du blog, écrit après décision humaine.

L'écriture est atomique (fichier temporaire + `os.replace`) pour ne jamais
laisser un `.mdx` à moitié écrit que Next.js essaierait de builder.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from ...domain.entities.article import Article
from ...domain.errors import PublicationError
from ...domain.ports.publishing import ArticleWriterPort, WriteResult
from ...shared.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)


class MdxArticleWriter(ArticleWriterPort):
    """Sérialise et écrit l'article sur disque."""

    def __init__(self, default_dir: Path) -> None:
        self.default_dir = default_dir

    def write(
        self,
        article: Article,
        *,
        destination: Path | None = None,
        overwrite: bool = False,
    ) -> WriteResult:
        target_dir = destination or self.default_dir
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PublicationError(f"Dossier de destination inaccessible ({target_dir}) : {exc}") from exc

        path = target_dir / article.slug.filename
        existed = path.exists()
        if existed and not overwrite:
            # Collision de slug : on suffixe par la date plutôt que d'écraser un article publié.
            path = target_dir / f"{article.slug.value}-{date.today().isoformat()}.mdx"
            logger.warning("Slug déjà utilisé — écriture sous %s", path.name)
            existed = path.exists()

        content = article.to_mdx()
        try:
            atomic_write_text(path, content)
        except OSError as exc:
            raise PublicationError(f"Écriture impossible de {path} : {exc}") from exc

        size = len(content.encode("utf-8"))
        logger.info("Article écrit : %s (%s octets, %s mots)", path, size, article.word_count)
        return WriteResult(path=path, bytes_written=size, overwritten=existed and overwrite)
