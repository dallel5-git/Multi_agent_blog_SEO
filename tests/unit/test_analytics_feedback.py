"""Tests de `AnalyticsPort.build_feedback` (issue #37).

Cette règle métier (mots-clés gagnants, articles sous-performants, pistes en
position 11-30) est partagée par tous les adapters — `FileAnalyticsStub` et
`SearchConsoleAnalytics` en héritent sans la redéfinir. On la teste ici une
fois, au niveau du port, plutôt que dans chaque adapter.
"""

from __future__ import annotations

from blogseo.domain.ports.analytics import AnalyticsPort, ArticlePerformance


class _StubPort(AnalyticsPort):
    """Sous-classe minimale : seul `build_feedback` (hérité) nous intéresse ici."""

    def fetch_performance(self, *, days: int = 28):
        return []


PORT = _StubPort()


class TestAucuneDonnee:
    def test_feedback_vide_sans_performances(self):
        feedback = PORT.build_feedback([])
        assert feedback.is_empty


class TestMotsClesGagnants:
    def test_les_requetes_du_meilleur_ctr_remontent(self):
        # `build_feedback` ne retient que les 3 meilleurs CTR : il faut donc plus
        # de 3 articles pour que le moins bon soit effectivement écarté.
        performances = [
            ArticlePerformance(slug="a", impressions=1000, clicks=200,
                               top_queries=("meilleur mot-clé", "autre mot-clé")),
            ArticlePerformance(slug="b", impressions=1000, clicks=150, top_queries=("second",)),
            ArticlePerformance(slug="c", impressions=1000, clicks=100, top_queries=("troisième",)),
            ArticlePerformance(slug="d", impressions=1000, clicks=1, top_queries=("mot-clé faible",)),
        ]
        feedback = PORT.build_feedback(performances)
        assert "meilleur mot-clé" in feedback.winning_keywords
        assert "mot-clé faible" not in feedback.winning_keywords


class TestArticlesSousPerformants:
    def test_forte_impression_faible_ctr_est_signale(self):
        performances = [
            ArticlePerformance(slug="a-oublier", impressions=500, clicks=2),   # ctr = 0.004
            ArticlePerformance(slug="ca-marche", impressions=500, clicks=100),  # ctr = 0.2
        ]
        feedback = PORT.build_feedback(performances)
        assert feedback.underperforming_slugs == ["a-oublier"]

    def test_peu_d_impressions_n_est_jamais_signale_meme_a_ctr_nul(self):
        performances = [ArticlePerformance(slug="trop-recent", impressions=5, clicks=0)]
        feedback = PORT.build_feedback(performances)
        assert feedback.underperforming_slugs == []


class TestPistesPage2:
    def test_position_11_a_30_remonte_comme_piste(self):
        performances = [
            ArticlePerformance(slug="page2", impressions=200, clicks=5,
                               average_position=18.0, top_queries=("piste page 2",)),
            ArticlePerformance(slug="page1", impressions=200, clicks=50,
                               average_position=3.0, top_queries=("déjà en tête",)),
        ]
        feedback = PORT.build_feedback(performances)
        assert "piste page 2" in feedback.suggested_topics
        assert "déjà en tête" not in feedback.suggested_topics

    def test_position_exactement_10_n_est_pas_une_piste(self):
        performances = [ArticlePerformance(slug="p10", impressions=200, clicks=5,
                                           average_position=10.0, top_queries=("limite",))]
        assert PORT.build_feedback(performances).suggested_topics == []

    def test_position_au_dela_de_30_n_est_pas_une_piste(self):
        performances = [ArticlePerformance(slug="p31", impressions=200, clicks=5,
                                           average_position=31.0, top_queries=("trop loin",))]
        assert PORT.build_feedback(performances).suggested_topics == []
