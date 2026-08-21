"""Tests des adapters neutres `NullSearch` / `NullTrends` (mode `--offline`)."""

from __future__ import annotations

from blogseo.infrastructure.search.null_search import NullSearch
from blogseo.infrastructure.trends.null_trends import NullTrends


class TestNullSearch:
    def test_ne_renvoie_jamais_de_resultat(self):
        search = NullSearch()
        assert search.search("automatisation n8n Tunisie") == []
        assert search.search_news("actualité tech") == []

    def test_n_est_jamais_disponible(self):
        assert NullSearch().is_available() is False


class TestNullTrends:
    def test_aucun_interet_calcule(self):
        trends = NullTrends()
        assert trends.interest_over_time(["python", "n8n"]) == {}

    def test_aucune_requete_associee(self):
        assert NullTrends().related_queries("python") == []

    def test_n_est_jamais_disponible(self):
        assert NullTrends().is_available() is False
