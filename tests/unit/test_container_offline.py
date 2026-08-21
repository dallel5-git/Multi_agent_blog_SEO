"""Tests du câblage `--offline` dans le composition root (issue #30).

`--offline` doit désactiver TOUT appel réseau : LLM factice (déjà couvert
ailleurs), mais aussi recherche web, Google Trends, sources de veille tech et
flux RSS tunisiens — pas seulement Telegram et la génération d'image.
"""

from __future__ import annotations

from blogseo.infrastructure.config.container import Container
from blogseo.infrastructure.config.settings import Settings, SourcesSettings, StorageSettings
from blogseo.infrastructure.llm.fake import FakeLLM
from blogseo.infrastructure.notifications.telegram import NullNotifier
from blogseo.infrastructure.search.null_search import NullSearch
from blogseo.infrastructure.trends.null_trends import NullTrends
from blogseo.infrastructure.trends.pytrends_adapter import PyTrendsAdapter


def make_settings(tmp_path, **overrides) -> Settings:
    return Settings(storage=StorageSettings(root=tmp_path), **overrides)


class TestModeHorsLigne:
    def test_llm_factice_sans_cle(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=True)
        assert isinstance(container.llm, FakeLLM)

    def test_aucune_recherche_web(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=True)
        assert isinstance(container.search, NullSearch)
        assert container.search.search("n'importe quoi") == []
        assert container.search.is_available() is False

    def test_aucun_appel_google_trends(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=True)
        assert isinstance(container.trends, NullTrends)
        assert container.trends.interest_over_time(["python"]) == {}

    def test_aucune_source_de_veille_mondiale(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=True)
        assert container.global_sources == []

    def test_aucun_flux_rss_tunisien_meme_si_configure_dans_env(self, tmp_path):
        settings = make_settings(
            tmp_path, sources=SourcesSettings(tunisia_rss_feeds=("https://example.com/rss",))
        )
        container = Container(settings, offline=True)
        assert container.tunisia_rss is None

    def test_generation_d_image_desactivee(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=True)
        assert container.image_generator is None

    def test_telegram_remplace_par_le_notifier_neutre(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=True)
        assert isinstance(container.telegram, NullNotifier)

    def test_verification_des_liens_desactivee_chez_le_relecteur(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=True)
        assert container.agents.technical_reviewer.check_links is False


class TestModeEnLigneParDefaut:
    """Sans --offline, les adapters réseau réels sont utilisés (même sans clé)."""

    def test_recherche_web_reelle_par_defaut(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=False)
        assert not isinstance(container.search, NullSearch)

    def test_trends_reel_par_defaut(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=False)
        assert isinstance(container.trends, PyTrendsAdapter)

    def test_sources_de_veille_mondiale_presentes_par_defaut(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=False)
        assert len(container.global_sources) > 0

    def test_llm_factice_si_aucune_cle_meme_en_ligne(self, tmp_path):
        # Pas de CEREBRAS_API_KEY/GROQ_API_KEY dans l'environnement de test : repli sur FakeLLM.
        container = Container(make_settings(tmp_path), offline=False)
        assert isinstance(container.llm, FakeLLM)
