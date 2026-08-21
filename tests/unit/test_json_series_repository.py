"""Tests de la persistance JSON des séries (issue #41)."""

from __future__ import annotations

import time

from blogseo.domain.entities.series import ArticleSeries, SeriesTopic
from blogseo.domain.value_objects.category import Category
from blogseo.infrastructure.persistence.json_series_repository import JsonSeriesRepository


def make_series(theme: str = "n8n", status: str = "pending") -> ArticleSeries:
    return ArticleSeries(
        theme=theme,
        title=f"Série {theme}",
        topics=[
            SeriesTopic(
                title="Sujet 1", angle="angle", category=Category.N8N,
                primary_keyword="mot-clé", secondary_keywords=("a", "b"),
                outline=("Intro", "Conclusion"), status=status,
            ),
        ],
    )


class TestRoundTrip:
    def test_save_puis_get_restitue_la_serie(self, tmp_path):
        repo = JsonSeriesRepository(tmp_path)
        series = make_series()

        repo.save(series)
        loaded = repo.get(series.series_id)

        assert loaded is not None
        assert loaded.series_id == series.series_id
        assert loaded.theme == "n8n"
        assert len(loaded.topics) == 1
        assert loaded.topics[0].title == "Sujet 1"
        assert loaded.topics[0].category == Category.N8N
        assert loaded.topics[0].secondary_keywords == ("a", "b")
        assert loaded.topics[0].outline == ("Intro", "Conclusion")

    def test_get_inexistant_renvoie_none(self, tmp_path):
        repo = JsonSeriesRepository(tmp_path)
        assert repo.get("serie-inconnue") is None


class TestFindActive:
    def test_renvoie_la_plus_recente_avec_un_sujet_en_attente(self, tmp_path):
        repo = JsonSeriesRepository(tmp_path)
        old = make_series(theme="ancienne", status="published")
        old.topics[0].slug = "ancien-slug"
        repo.save(old)
        time.sleep(0.01)
        recent = make_series(theme="recente", status="pending")
        repo.save(recent)

        active = repo.find_active()
        assert active is not None
        assert active.series_id == recent.series_id

    def test_none_si_aucune_serie_active(self, tmp_path):
        repo = JsonSeriesRepository(tmp_path)
        done = make_series(status="published")
        done.topics[0].slug = "slug"
        repo.save(done)

        assert repo.find_active() is None


def test_list_all_trie_du_plus_recent_au_plus_ancien(tmp_path):
    repo = JsonSeriesRepository(tmp_path)
    first = make_series(theme="premiere")
    repo.save(first)
    time.sleep(0.01)
    second = make_series(theme="seconde")
    repo.save(second)

    listed = repo.list_all()
    assert [s.theme for s in listed] == ["seconde", "premiere"]
