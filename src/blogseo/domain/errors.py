"""Exceptions métier du pipeline.

Toutes héritent de `BlogSeoError` pour que l'orchestrateur puisse distinguer une
erreur attendue (quota, doublon) d'un vrai bug Python.
"""

from __future__ import annotations


class BlogSeoError(Exception):
    """Erreur racine du domaine."""


class ConfigurationError(BlogSeoError):
    """Configuration invalide ou clé d'API manquante."""


class LLMError(BlogSeoError):
    """Échec générique d'un fournisseur LLM."""


class QuotaExceededError(LLMError):
    """Quota gratuit atteint (HTTP 429) : déclenche le fallback Cerebras → Groq."""


class AllProvidersFailedError(LLMError):
    """Tous les fournisseurs LLM configurés ont échoué."""


class SearchError(BlogSeoError):
    """Échec d'une recherche web (non bloquant : dégradation gracieuse)."""


class DuplicateTopicError(BlogSeoError):
    """Le sujet retenu est un quasi-doublon d'un article déjà publié."""

    def __init__(self, title: str, similar_slug: str, score: float) -> None:
        super().__init__(
            f"Sujet « {title} » trop proche de l'article existant « {similar_slug} » "
            f"(similarité {score:.2%})"
        )
        self.title = title
        self.similar_slug = similar_slug
        self.score = score


class QualityGateRejectedError(BlogSeoError):
    """L'article n'a pas passé le Quality Gate après le nombre max d'itérations."""


class PublicationError(BlogSeoError):
    """Échec d'écriture du fichier ou de l'opération Git."""


class NotificationError(BlogSeoError):
    """Échec d'envoi ou de réception d'une notification Telegram."""


class ReviewTimeoutError(BlogSeoError):
    """Aucune décision humaine reçue dans le délai imparti."""
