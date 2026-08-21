"""Tests de l'enrichissement de la veille tunisienne (issue #38).

Vérifie que les 5 flux RSS vérifiés et les requêtes sectorielles/villes/
programmes sont bien les valeurs par défaut, et que `TUNISIA_RSS_FEEDS`
reste surchargeable (y compris pour désactiver la source explicitement).
"""

from __future__ import annotations

from blogseo.infrastructure.config.settings import SourcesSettings
from blogseo.infrastructure.sources.rss import DEFAULT_TUNISIA_FEEDS


class TestFluxRssParDefaut:
    def test_cinq_flux_verifies_par_defaut(self):
        assert len(DEFAULT_TUNISIA_FEEDS) == 5
        assert SourcesSettings().tunisia_rss_feeds == DEFAULT_TUNISIA_FEEDS

    def test_tous_les_flux_sont_des_url_https(self):
        for feed in DEFAULT_TUNISIA_FEEDS:
            assert feed.startswith("https://")

    def test_aucun_doublon_de_domaine(self):
        domains = [feed.split("/")[2] for feed in DEFAULT_TUNISIA_FEEDS]
        assert len(domains) == len(set(domains))


class TestRequetesSpecifiques:
    def test_couvre_secteurs_villes_et_programmes(self):
        queries = " ".join(SourcesSettings().tunisia_queries).lower()
        # Secteurs.
        assert "fintech" in queries
        assert "agritech" in queries
        # Villes hors Tunis.
        assert "sfax" in queries
        assert "sousse" in queries
        # Programmes d'accompagnement.
        assert "flat6labs" in queries or "smart tunisia" in queries

    def test_les_requetes_historiques_sont_conservees(self):
        queries = SourcesSettings().tunisia_queries
        assert "loi startup act Tunisie numérique" in queries
        assert "PME tunisienne digitalisation automatisation" in queries

    def test_au_moins_huit_requetes(self):
        assert len(SourcesSettings().tunisia_queries) >= 8


class TestSurchargeEnvironnement:
    def test_from_env_retombe_sur_les_flux_par_defaut_si_absent(self, monkeypatch):
        from blogseo.infrastructure.config.settings import Settings

        monkeypatch.delenv("TUNISIA_RSS_FEEDS", raising=False)
        settings = Settings.from_env()
        assert settings.sources.tunisia_rss_feeds == DEFAULT_TUNISIA_FEEDS

    def test_valeur_vide_explicite_desactive_la_source(self, monkeypatch):
        from blogseo.infrastructure.config.settings import Settings

        monkeypatch.setenv("TUNISIA_RSS_FEEDS", "")
        settings = Settings.from_env()
        assert settings.sources.tunisia_rss_feeds == ()

    def test_valeur_personnalisee_remplace_les_flux_par_defaut(self, monkeypatch):
        from blogseo.infrastructure.config.settings import Settings

        monkeypatch.setenv("TUNISIA_RSS_FEEDS", "https://exemple-perso.tn/feed")
        settings = Settings.from_env()
        assert settings.sources.tunisia_rss_feeds == ("https://exemple-perso.tn/feed",)
