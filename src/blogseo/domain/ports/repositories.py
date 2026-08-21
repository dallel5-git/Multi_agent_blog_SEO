"""Ports de persistance : historique des articles (anti-doublon) et runs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..entities.pipeline_run import PipelineRun
from ..entities.series import ArticleSeries


@dataclass(frozen=True, slots=True)
class PublishedArticleRef:
    """Référence légère d'un article déjà publié, utilisée pour l'anti-doublon."""

    slug: str
    title: str
    description: str = ""
    category: str = ""
    date: str = ""
    tags: tuple[str, ...] = ()

    @property
    def embedding_text(self) -> str:
        """Texte projeté dans l'espace vectoriel pour la détection sémantique."""
        return f"{self.title}. {self.description} Catégorie : {self.category}. Tags : {', '.join(self.tags)}"


@dataclass(frozen=True, slots=True)
class SimilarityHit:
    """Voisin le plus proche trouvé dans le vector store."""

    slug: str
    title: str
    score: float  # similarité cosinus, 0.0 (rien à voir) → 1.0 (identique)


class ArticleHistoryPort(ABC):
    """Historique sémantique des articles publiés (implémentation : ChromaDB local)."""

    @abstractmethod
    def index(self, articles: list[PublishedArticleRef]) -> int:
        """(Ré)indexe les articles. Renvoie le nombre d'entrées indexées."""

    @abstractmethod
    def find_similar(self, text: str, *, top_k: int = 3) -> list[SimilarityHit]:
        """Renvoie les articles les plus proches sémantiquement de `text`."""

    @abstractmethod
    def count(self) -> int:
        """Nombre d'articles actuellement indexés."""


class ArticleSourcePort(ABC):
    """Lecture des articles existants du blog (implémentation : dossier content/articles)."""

    @abstractmethod
    def list_published(self) -> list[PublishedArticleRef]:
        """Liste les articles `.mdx` présents dans le blog."""

    @abstractmethod
    def slugs(self) -> set[str]:
        """Ensemble des slugs déjà utilisés (collision de nom de fichier)."""


class RunRepositoryPort(ABC):
    """Persistance des runs, nécessaire à la validation humaine différée."""

    @abstractmethod
    def save(self, run: PipelineRun) -> None: ...

    @abstractmethod
    def get(self, run_id: str) -> PipelineRun | None: ...

    @abstractmethod
    def list_awaiting_review(self) -> list[PipelineRun]: ...

    @abstractmethod
    def list_recent(self, limit: int = 20) -> list[PipelineRun]: ...


class SeriesRepositoryPort(ABC):
    """Persistance des séries d'articles (issue #41)."""

    @abstractmethod
    def save(self, series: ArticleSeries) -> None: ...

    @abstractmethod
    def get(self, series_id: str) -> ArticleSeries | None: ...

    @abstractmethod
    def find_active(self) -> ArticleSeries | None:
        """La série la plus récente ayant encore un sujet en attente, s'il y en a une."""

    @abstractmethod
    def list_all(self) -> list[ArticleSeries]: ...
