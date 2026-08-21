"""Tests de l'entité `ArticleSeries` (issue #41)."""

from __future__ import annotations

from blogseo.domain.entities.series import ArticleSeries, SeriesTopic
from blogseo.domain.value_objects.category import Category


def make_topic(title: str, status: str = "pending", slug: str = "") -> SeriesTopic:
    return SeriesTopic(
        title=title, angle="angle", category=Category.N8N,
        primary_keyword="mot-clé", status=status, slug=slug,
    )


class TestNextPending:
    def test_renvoie_le_premier_sujet_en_attente(self):
        series = ArticleSeries(theme="n8n", title="Série n8n", topics=[
            make_topic("1", status="published", slug="un"),
            make_topic("2", status="pending"),
            make_topic("3", status="pending"),
        ])
        assert series.next_pending().title == "2"

    def test_none_si_tout_est_traite(self):
        series = ArticleSeries(theme="n8n", title="Série n8n", topics=[
            make_topic("1", status="published", slug="un"),
            make_topic("2", status="skipped"),
        ])
        assert series.next_pending() is None


class TestPublishedTopics:
    def test_ne_garde_que_les_sujets_publies_dans_l_ordre(self):
        series = ArticleSeries(theme="n8n", title="Série n8n", topics=[
            make_topic("1", status="published", slug="un"),
            make_topic("2", status="written", slug="deux"),
            make_topic("3", status="published", slug="trois"),
        ])
        assert [t.title for t in series.published_topics()] == ["1", "3"]


class TestIsActive:
    def test_actif_tant_qu_un_sujet_est_en_attente(self):
        series = ArticleSeries(theme="n8n", title="Série n8n", topics=[make_topic("1")])
        assert series.is_active

    def test_inactif_une_fois_tous_traites(self):
        series = ArticleSeries(theme="n8n", title="Série n8n", topics=[
            make_topic("1", status="published", slug="un"),
            make_topic("2", status="skipped"),
        ])
        assert not series.is_active


def test_summary_compte_les_articles_publies():
    series = ArticleSeries(theme="n8n", title="Série n8n", topics=[
        make_topic("1", status="published", slug="un"),
        make_topic("2", status="pending"),
        make_topic("3", status="pending"),
    ])
    assert "1/3" in series.summary()
