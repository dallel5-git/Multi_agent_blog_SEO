"""Ports de sortie : écriture du fichier, opérations Git, génération d'image."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..entities.article import Article


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Résultat d'une écriture de fichier `.mdx`."""

    path: Path
    bytes_written: int
    overwritten: bool = False


@dataclass(frozen=True, slots=True)
class PushResult:
    """Résultat d'un commit/push Git."""

    committed: bool
    pushed: bool
    commit_sha: str = ""
    branch: str = ""
    message: str = ""


class ArticleWriterPort(ABC):
    """Écrit un article au format `.mdx` dans un dossier cible."""

    @abstractmethod
    def write(self, article: Article, *, destination: Path | None = None, overwrite: bool = False) -> WriteResult:
        """Sérialise l'article et l'écrit sur disque."""


class GitPublisherPort(ABC):
    """Commit + push du dépôt du blog (déclenche le déploiement Vercel)."""

    @abstractmethod
    def commit_and_push(self, paths: list[Path], message: str) -> PushResult:
        """Ajoute les fichiers, commit et pousse sur la branche configurée."""

    @abstractmethod
    def is_clean(self) -> bool:
        """Vrai si le dépôt n'a aucune modification non commitée (hors nos fichiers)."""


class SeriesBacklinkPort(ABC):
    """Réécrit un article déjà publié pour y injecter la section « Cette série »."""

    @abstractmethod
    def update(self, slug: str, entries: list[tuple[str, str]]) -> Path | None:
        """`entries` = [(slug, titre), ...] à lier. Renvoie le chemin modifié, ou None
        si l'article est introuvable ou si le contenu n'a pas changé."""


class ImageGeneratorPort(ABC):
    """Génère l'image de couverture (implémentation par défaut : Pollinations.ai)."""

    name: str = "image"

    @abstractmethod
    def generate(self, prompt: str, *, slug: str, width: int = 1280, height: int = 720) -> Path | None:
        """Génère et enregistre l'image. Renvoie None si l'API échoue (image de secours utilisée)."""


@dataclass(frozen=True, slots=True)
class ExistingArticle:
    """Article déjà publié, relu depuis le disque pour un refresh ciblé (issue #42)."""

    slug: str
    title: str
    description: str
    category: str
    body_markdown: str


class ArticleRefreshPort(ABC):
    """Relit un article publié et n'en réécrit que le titre/la description.

    Le corps n'est jamais modifié : un article avec beaucoup d'impressions et
    peu de clics a un problème de titre/description, pas de fond (issue #42).
    """

    @abstractmethod
    def read(self, slug: str) -> ExistingArticle | None:
        """Relit l'article publié. `None` si le slug est introuvable."""

    @abstractmethod
    def update_metadata(self, slug: str, *, title: str, description: str) -> Path | None:
        """Réécrit uniquement `title`/`description` dans le frontmatter, en place.

        Ne touche ni au corps, ni au nom de fichier (donc ni au slug, ni à
        l'URL). Renvoie le chemin modifié, ou `None` si le slug est introuvable.
        """
