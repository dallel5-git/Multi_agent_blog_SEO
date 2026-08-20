"""Adapter d'embeddings 100 % local : `sentence-transformers` sur CPU.

Modèle par défaut `all-MiniLM-L6-v2` (~90 Mo, 384 dimensions) : téléchargé une
seule fois depuis Hugging Face, puis mis en cache. Aucune clé d'API, aucun appel
réseau lors des runs suivants.

Un repli déterministe (hachage de n-grammes) est fourni pour que les tests et le
mode hors ligne fonctionnent même sans le modèle installé.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re

from ...domain.ports.embeddings import EmbeddingPort

logger = logging.getLogger(__name__)


class SentenceTransformerEmbeddings(EmbeddingPort):
    """Encodeur local, chargé paresseusement au premier appel."""

    name = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", *, allow_fallback: bool = True) -> None:
        self.model_name = model_name
        self.allow_fallback = allow_fallback
        self._model = None
        self._failed = False
        self.dimension = 384

    def _get_model(self):
        if self._model is not None or self._failed:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

            logger.info("Chargement du modèle d'embeddings « %s » (CPU, local)…", self.model_name)
            self._model = SentenceTransformer(self.model_name, device="cpu")
            self.dimension = self._model.get_sentence_embedding_dimension()
        except Exception as exc:  # noqa: BLE001
            self._failed = True
            if not self.allow_fallback:
                raise
            logger.warning(
                "sentence-transformers indisponible (%s) : repli sur l'encodeur de hachage. "
                "La détection de doublons sera moins fine.", exc,
            )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        if model is None:
            return [_hash_embedding(t, self.dimension) for t in texts]
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [list(map(float, vector)) for vector in vectors]


# --------------------------------------------------------------------------- #
# Repli déterministe : « hashing trick » sur des n-grammes de mots
# --------------------------------------------------------------------------- #
_TOKEN_PATTERN = re.compile(r"\b[\wÀ-ÿ]+\b", re.UNICODE)


def _hash_embedding(text: str, dimension: int = 384) -> list[float]:
    """Vecteur normalisé obtenu par hachage de tokens et bigrammes.

    Ce n'est pas de la vraie sémantique, mais c'est stable, sans dépendance, et
    suffisant pour attraper les doublons quasi littéraux.
    """
    tokens = [t.lower() for t in _TOKEN_PATTERN.findall(text)]
    grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
    vector = [0.0] * dimension
    for gram in grams:
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector
