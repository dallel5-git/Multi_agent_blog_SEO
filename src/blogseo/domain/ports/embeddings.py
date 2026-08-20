"""Port `EmbeddingPort` : vectorisation de texte (implémentation locale CPU)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingPort(ABC):
    """Contrat d'encodage de texte en vecteurs denses.

    L'implémentation par défaut utilise `sentence-transformers` avec le modèle
    `all-MiniLM-L6-v2` : 100 % local, sur CPU, sans aucune clé d'API.
    """

    name: str = "embeddings"
    dimension: int = 384

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Encode une liste de textes. L'ordre de sortie suit l'ordre d'entrée."""

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
