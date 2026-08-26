"""Écriture atomique d'un fichier texte (fichier temporaire + `os.replace`).

Partagé par tous les adapters qui écrivent dans `content/articles/` : un
`.mdx` à moitié écrit ferait planter le build Next.js, que ce soit une
écriture complète (`MdxArticleWriter`) ou une réécriture ciblée du
frontmatter (refresh, issue #42).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
