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


class ImageGeneratorPort(ABC):
    """Génère l'image de couverture (implémentation par défaut : Pollinations.ai)."""

    name: str = "image"

    @abstractmethod
    def generate(self, prompt: str, *, slug: str, width: int = 1280, height: int = 720) -> Path | None:
        """Génère et enregistre l'image. Renvoie None si l'API échoue (image de secours utilisée)."""
