"""Tests du câblage `AnalyticsPort` dans le composition root (issue #37).

`SearchConsoleAnalytics` doit être choisi uniquement quand la configuration
est complète et que le pipeline n'est pas en mode `--offline` ; sinon, repli
sur `FileAnalyticsStub` — sans qu'aucun agent n'ait besoin de le savoir.
"""

from __future__ import annotations

from blogseo.infrastructure.analytics.search_console import SearchConsoleAnalytics
from blogseo.infrastructure.analytics.stub import FileAnalyticsStub
from blogseo.infrastructure.config.container import Container
from blogseo.infrastructure.config.settings import SearchConsoleSettings, Settings, StorageSettings

CONFIGURED = SearchConsoleSettings(
    site_url="https://exemple.com/",
    client_id="client-id",
    client_secret="client-secret",
    refresh_token="refresh-token",
)


def make_settings(tmp_path, **overrides) -> Settings:
    return Settings(storage=StorageSettings(root=tmp_path), **overrides)


class TestSearchConsoleConfigure:
    def test_utilise_search_console_quand_configure_et_en_ligne(self, tmp_path):
        container = Container(make_settings(tmp_path, search_console=CONFIGURED), offline=False)
        assert isinstance(container.analytics, SearchConsoleAnalytics)

    def test_repli_sur_le_stub_meme_configure_en_mode_offline(self, tmp_path):
        container = Container(make_settings(tmp_path, search_console=CONFIGURED), offline=True)
        assert isinstance(container.analytics, FileAnalyticsStub)


class TestSearchConsoleNonConfigure:
    def test_repli_sur_le_stub_par_defaut(self, tmp_path):
        container = Container(make_settings(tmp_path), offline=False)
        assert isinstance(container.analytics, FileAnalyticsStub)

    def test_repli_sur_le_stub_si_partiellement_configure(self, tmp_path):
        partiel = SearchConsoleSettings(site_url="https://exemple.com/", client_id="client-id")
        container = Container(make_settings(tmp_path, search_console=partiel), offline=False)
        assert isinstance(container.analytics, FileAnalyticsStub)
