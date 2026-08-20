"""Value object `Slug` : identifiant d'URL d'un article.

Le slug devient le nom du fichier `content/articles/<slug>.mdx` et l'URL
`/blog/<slug>`. Il doit donc être stable, ASCII, sans accent ni espace.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_LENGTH = 70

# Mots vides français retirés du slug : ils diluent le signal SEO.
_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "et", "ou",
    "en", "au", "aux", "pour", "par", "sur", "dans", "avec", "sans", "ce",
    "cet", "cette", "ces", "son", "sa", "ses", "vos", "votre", "the", "a",
    "an", "of", "to", "in",
}


@dataclass(frozen=True, slots=True)
class Slug:
    """Slug validé et immuable."""

    value: str

    def __post_init__(self) -> None:
        if not _SLUG_PATTERN.match(self.value):
            raise ValueError(f"Slug invalide : {self.value!r}")

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value

    @property
    def filename(self) -> str:
        """Nom de fichier attendu par le blog Next.js."""
        return f"{self.value}.mdx"

    @classmethod
    def from_title(cls, title: str, max_length: int = _MAX_LENGTH) -> Slug:
        """Dérive un slug propre à partir d'un titre français accentué."""
        # 1. Décomposition Unicode puis suppression des diacritiques (é -> e).
        decomposed = unicodedata.normalize("NFKD", title)
        ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))

        # 2. Tout ce qui n'est pas alphanumérique devient un séparateur.
        lowered = ascii_only.lower()
        tokens = [t for t in re.split(r"[^a-z0-9]+", lowered) if t]

        # 3. Retrait des mots vides, sauf si cela viderait complètement le slug.
        meaningful = [t for t in tokens if t not in _STOPWORDS]
        tokens = meaningful or tokens
        if not tokens:
            raise ValueError(f"Impossible de dériver un slug depuis {title!r}")

        # 4. Troncature sur une frontière de mot pour rester lisible.
        slug = ""
        for token in tokens:
            candidate = f"{slug}-{token}" if slug else token
            if len(candidate) > max_length:
                break
            slug = candidate
        if not slug:
            slug = tokens[0][:max_length].rstrip("-")

        return cls(slug)
