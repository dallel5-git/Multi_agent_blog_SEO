"""Tests de `SearchConsoleAnalytics` (issue #37).

Le vrai réseau est simulé par `FakeSession` : on vérifie le rafraîchissement
du token OAuth, le mapping des lignes `page` × `query` vers `ArticlePerformance`,
et la dégradation gracieuse (jamais d'exception propagée au pipeline).
"""

from __future__ import annotations

import pytest

from blogseo.infrastructure.analytics.search_console import SearchConsoleAnalytics


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Distingue les appels au endpoint token de ceux à searchAnalytics/query."""

    def __init__(self, *, token_response=None, query_responses=None) -> None:
        self.token_response = token_response or FakeResponse({"access_token": "tok-1", "expires_in": 3600})
        self.query_responses = list(query_responses or [FakeResponse({"rows": []})])
        self.token_calls = 0
        self.query_calls = 0

    def post(self, url, *, data=None, json=None, headers=None, timeout=None):
        if "oauth2.googleapis.com" in url:
            self.token_calls += 1
            return self.token_response
        self.query_calls += 1
        return self.query_responses.pop(0) if self.query_responses else FakeResponse({"rows": []})


def make_analytics(session: FakeSession, **overrides) -> SearchConsoleAnalytics:
    params = {
        "site_url": "https://exemple.com/",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "refresh_token": "refresh-token",
        "session": session,
    }
    params.update(overrides)
    return SearchConsoleAnalytics(**params)


def row(page: str, query: str, *, impressions: int, clicks: int, position: float) -> dict:
    return {"keys": [page, query], "impressions": impressions, "clicks": clicks, "position": position}


class TestDisponibilite:
    def test_disponible_si_tout_est_configure(self):
        assert make_analytics(FakeSession()).is_available() is True

    def test_indisponible_si_le_refresh_token_manque(self):
        assert make_analytics(FakeSession(), refresh_token="").is_available() is False

    def test_non_configure_ne_fait_aucun_appel_reseau(self):
        session = FakeSession()
        analytics = make_analytics(session, site_url="")

        assert analytics.fetch_performance() == []
        assert session.token_calls == 0
        assert session.query_calls == 0


class TestRafraichissementDuToken:
    def test_un_seul_appel_token_par_fetch(self):
        session = FakeSession(query_responses=[FakeResponse({"rows": []})])
        make_analytics(session).fetch_performance()

        assert session.token_calls == 1
        assert session.query_calls == 1

    def test_token_expire_est_redemande(self):
        session = FakeSession(
            token_response=FakeResponse({"access_token": "tok-1", "expires_in": -100}),  # déjà expiré
            query_responses=[FakeResponse({"rows": []}), FakeResponse({"rows": []})],
        )
        analytics = make_analytics(session)

        analytics.fetch_performance()
        analytics.fetch_performance()

        assert session.token_calls == 2


class TestMappingVersArticlePerformance:
    def test_agrege_plusieurs_requetes_pour_le_meme_slug(self):
        rows = [
            row("https://exemple.com/blog/mon-article", "requête populaire",
                impressions=100, clicks=8, position=6.0),
            row("https://exemple.com/blog/mon-article", "requête rare",
                impressions=20, clicks=0, position=22.0),
        ]
        session = FakeSession(query_responses=[FakeResponse({"rows": rows})])

        performances = make_analytics(session).fetch_performance()

        assert len(performances) == 1
        perf = performances[0]
        assert perf.slug == "mon-article"
        assert perf.impressions == 120
        assert perf.clicks == 8
        assert perf.top_queries[0] == "requête populaire"  # triée par impressions décroissantes

    def test_la_page_d_accueil_du_blog_est_ignoree(self):
        rows = [row("https://exemple.com/blog", "n8n tunisie", impressions=500, clicks=10, position=5.0)]
        session = FakeSession(query_responses=[FakeResponse({"rows": rows})])

        assert make_analytics(session).fetch_performance() == []

    def test_position_moyenne_ponderee_par_les_impressions(self):
        rows = [
            row("https://exemple.com/blog/article", "q1", impressions=90, clicks=5, position=10.0),
            row("https://exemple.com/blog/article", "q2", impressions=10, clicks=0, position=50.0),
        ]
        session = FakeSession(query_responses=[FakeResponse({"rows": rows})])

        perf = make_analytics(session).fetch_performance()[0]
        # (90 * 10.0 + 10 * 50.0) / 100 = 14.0
        assert perf.average_position == pytest.approx(14.0, abs=0.1)


class TestDegradationGracieuse:
    def test_token_refuse_ne_leve_pas_et_renvoie_liste_vide(self):
        session = FakeSession(token_response=FakeResponse({"error": "invalid_grant"}, status_code=400))
        analytics = make_analytics(session)

        assert analytics.fetch_performance() == []

    def test_erreur_api_ne_leve_pas_et_renvoie_liste_vide(self):
        # `_query` retente 2 fois (voir @retry sur SearchConsoleAnalytics._query) avant d'abandonner.
        session = FakeSession(query_responses=[FakeResponse({}, status_code=500, text="server error")] * 2)
        analytics = make_analytics(session)

        assert analytics.fetch_performance() == []
