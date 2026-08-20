"""Tests du mécanisme anti-doublon (embeddings + index vectoriel).

On teste avec l'encodeur de repli déterministe : pas de téléchargement de modèle,
tests rapides et reproductibles en CI.
"""

from __future__ import annotations

import pytest

from blogseo.domain.ports.embeddings import EmbeddingPort
from blogseo.domain.ports.repositories import PublishedArticleRef
from blogseo.infrastructure.embeddings.sentence_transformers_adapter import (
    SentenceTransformerEmbeddings,
    _hash_embedding,
)
from blogseo.infrastructure.vectorstore.chroma_history import ChromaArticleHistory, _cosine


class DeterministicEmbeddings(EmbeddingPort):
    """Encodeur de test : le « hashing trick », sans dépendance ni réseau."""

    name = "test"
    dimension = 128

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embedding(t, self.dimension) for t in texts]


@pytest.fixture
def history(tmp_path) -> ChromaArticleHistory:
    return ChromaArticleHistory(DeterministicEmbeddings(), tmp_path / "vectors")


ARTICLES = [
    PublishedArticleRef(
        slug="automatiser-workflows-n8n",
        title="Automatiser ses workflows avec n8n",
        description="Guide complet pour automatiser vos tâches répétitives avec n8n.",
        category="n8n",
        tags=("n8n", "automatisation"),
    ),
    PublishedArticleRef(
        slug="agents-ia-python-langchain",
        title="Créer votre premier agent IA autonome avec Python",
        description="Construisez un agent capable de raisonner et d'utiliser des outils.",
        category="Agents IA",
        tags=("python", "agents"),
    ),
]


class TestEncodeurDeRepli:
    def test_produit_un_vecteur_normalise(self):
        vector = _hash_embedding("automatisation n8n", 128)
        assert len(vector) == 128
        assert _cosine(vector, vector) == pytest.approx(1.0, abs=1e-6)

    def test_est_deterministe(self):
        assert _hash_embedding("même texte", 64) == _hash_embedding("même texte", 64)

    def test_textes_differents_donnent_des_vecteurs_differents(self):
        a = _hash_embedding("automatisation n8n workflow", 128)
        b = _hash_embedding("cuisine tunisienne recette couscous", 128)
        assert _cosine(a, b) < 0.5

    def test_l_adapter_retombe_sur_le_hachage_si_le_modele_manque(self):
        adapter = SentenceTransformerEmbeddings("modele-inexistant-xyz", allow_fallback=True)
        vectors = adapter.embed(["bonjour", "salut"])
        assert len(vectors) == 2
        assert len(vectors[0]) == adapter.dimension


class TestIndexAntiDoublon:
    def test_index_vide_ne_renvoie_rien(self, history):
        assert history.count() == 0
        assert history.find_similar("n'importe quoi") == []

    def test_indexation_puis_comptage(self, history):
        assert history.index(ARTICLES) == 2
        assert history.count() == 2

    def test_detecte_un_quasi_doublon(self, history):
        history.index(ARTICLES)
        hits = history.find_similar(
            "Automatiser ses workflows avec n8n. Guide complet pour automatiser vos "
            "tâches répétitives avec n8n. Catégorie : n8n. Tags : n8n, automatisation",
            top_k=1,
        )
        assert hits
        assert hits[0].slug == "automatiser-workflows-n8n"
        assert hits[0].score > 0.85

    def test_un_sujet_neuf_a_un_score_bas(self, history):
        history.index(ARTICLES)
        hits = history.find_similar(
            "Déclarer ses impôts en ligne en Tunisie : guide fiscal pour freelances", top_k=1
        )
        assert hits[0].score < 0.5

    def test_reindexation_est_idempotente(self, history):
        history.index(ARTICLES)
        history.index(ARTICLES)
        assert history.count() == 2

    def test_top_k_est_respecte(self, history):
        history.index(ARTICLES)
        assert len(history.find_similar("n8n automatisation", top_k=1)) == 1


class TestSeuilDeDecision:
    """Le seuil `DUPLICATE_THRESHOLD` sépare « original » de « doublon »."""

    def test_le_seuil_par_defaut_laisse_passer_un_sujet_proche_mais_distinct(self, history):
        history.index(ARTICLES)
        hits = history.find_similar(
            "Connecter n8n à une base de données PostgreSQL depuis la Tunisie", top_k=1
        )
        assert hits[0].score < 0.85
