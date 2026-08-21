"""Adaptateur du `SeriesBacklinkPort` : relit/réécrit les `.mdx` déjà publiés."""

from __future__ import annotations

import logging
from pathlib import Path

from ...domain.ports.publishing import SeriesBacklinkPort
from ...shared.series_linking import upsert_series_section

logger = logging.getLogger(__name__)


class SeriesBacklinkWriter(SeriesBacklinkPort):
    """Relit et réécrit un `.mdx` déjà publié pour y injecter la section série."""

    def __init__(self, blog_content_dir: Path) -> None:
        self.blog_content_dir = blog_content_dir

    def update(self, slug: str, entries: list[tuple[str, str]]) -> Path | None:
        path = self.blog_content_dir / f"{slug}.mdx"
        if not path.exists():
            logger.warning("Maillage série : article publié introuvable sur disque (%s)", path)
            return None
        try:
            body = path.read_text(encoding="utf-8")
            updated = upsert_series_section(body, entries)
            if updated == body:
                return None
            path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            logger.warning("Maillage série : écriture impossible pour %s : %s", path, exc)
            return None
        return path
