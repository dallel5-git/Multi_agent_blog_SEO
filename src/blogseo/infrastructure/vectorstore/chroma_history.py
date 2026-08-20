"""Historique sémantique des articles : ChromaDB local (SQLite embarqué).

Aucun serveur, aucun abonnement : la base vit dans `storage/chroma/`.
Si `chromadb` n'est pas installé, on bascule sur un index en mémoire/JSON qui
implémente le même port — le pipeline reste fonctionnel, seule la persistance
change.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from ...domain.ports.embeddings import EmbeddingPort
from ...domain.ports.repositories import ArticleHistoryPort, PublishedArticleRef, SimilarityHit

logger = logging.getLogger(__name__)

_COLLECTION = "published_articles"


class ChromaArticleHistory(ArticleHistoryPort):
    """Index vectoriel persistant des articles déjà publiés."""

    def __init__(self, embeddings: EmbeddingPort, persist_dir: Path) -> None:
        self.embeddings = embeddings
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._collection = self._open_collection()
        self._memory = _JsonVectorIndex(persist_dir / "fallback_index.json") if self._collection is None else None

    def _open_collection(self):
        try:
            import chromadb  # type: ignore[import-not-found]
            from chromadb.config import Settings as ChromaSettings  # type: ignore[import-not-found]

            client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
            # `embedding_function=None` : on fournit nous-mêmes les vecteurs, ce qui
            # garantit que Chroma n'essaie jamais d'appeler un service distant payant.
            return client.get_or_create_collection(
                name=_COLLECTION,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ChromaDB indisponible (%s) : repli sur un index JSON local", exc)
            return None

    # ------------------------------------------------------------------ #
    def index(self, articles: list[PublishedArticleRef]) -> int:
        if not articles:
            return 0
        texts = [a.embedding_text for a in articles]
        vectors = self.embeddings.embed(texts)
        metadatas = [
            {"slug": a.slug, "title": a.title, "category": a.category, "date": a.date}
            for a in articles
        ]

        if self._collection is not None:
            self._collection.upsert(
                ids=[a.slug for a in articles],
                embeddings=vectors,
                documents=texts,
                metadatas=metadatas,
            )
        else:
            assert self._memory is not None
            self._memory.upsert([a.slug for a in articles], vectors, metadatas)

        logger.info("Anti-doublon : %s article(s) indexé(s) (total %s)", len(articles), self.count())
        return len(articles)

    def find_similar(self, text: str, *, top_k: int = 3) -> list[SimilarityHit]:
        if self.count() == 0:
            return []
        vector = self.embeddings.embed_one(text)

        if self._collection is not None:
            result = self._collection.query(
                query_embeddings=[vector],
                n_results=min(top_k, self.count()),
                include=["metadatas", "distances"],
            )
            metadatas = (result.get("metadatas") or [[]])[0]
            distances = (result.get("distances") or [[]])[0]
            hits = [
                SimilarityHit(
                    slug=meta.get("slug", ""),
                    title=meta.get("title", ""),
                    # Chroma renvoie une distance cosinus ∈ [0, 2] → similarité = 1 - d.
                    score=round(max(0.0, 1.0 - float(distance)), 4),
                )
                for meta, distance in zip(metadatas, distances, strict=False)
            ]
        else:
            assert self._memory is not None
            hits = self._memory.query(vector, top_k)

        for hit in hits:
            logger.debug("Voisin : %s (%.2f%%)", hit.slug, hit.score * 100)
        return hits

    def count(self) -> int:
        if self._collection is not None:
            try:
                return int(self._collection.count())
            except Exception:  # noqa: BLE001 - défensif
                return 0
        assert self._memory is not None
        return self._memory.count()


class _JsonVectorIndex:
    """Index vectoriel minimal persisté en JSON (repli sans ChromaDB)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, dict] = {}
        if path.exists():
            try:
                self.entries = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.entries = {}

    def upsert(self, ids: list[str], vectors: list[list[float]], metadatas: list[dict]) -> None:
        for entry_id, vector, meta in zip(ids, vectors, metadatas, strict=True):
            self.entries[entry_id] = {"vector": vector, "meta": meta}
        self._save()

    def query(self, vector: list[float], top_k: int) -> list[SimilarityHit]:
        scored = [
            SimilarityHit(
                slug=entry["meta"].get("slug", entry_id),
                title=entry["meta"].get("title", ""),
                score=round(_cosine(vector, entry["vector"]), 4),
            )
            for entry_id, entry in self.entries.items()
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        return len(self.entries)

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.entries), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - défensif
            logger.debug("Index JSON non persisté : %s", exc)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
