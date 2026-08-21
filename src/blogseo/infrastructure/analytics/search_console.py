"""Adapter Search Console réel — ferme la boucle de rétroaction performance.

API REST directe (`searchconsole.googleapis.com`) via `requests` : pas de SDK
`google-api-python-client`, dans le même esprit que `CerebrasLLM`. L'API Search
Console elle-même est gratuite et sans quota payant ; seule l'authentification
OAuth 2.0 doit être mise en place une fois (voir `scripts/search_console_oauth.py`
et la section 10 de `.env.example`).

Une panne (token expiré, API indisponible, propriété non vérifiée) ne doit
jamais faire échouer le run : comme les autres sources de veille, on journalise
et on renvoie une liste vide plutôt que de lever.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from urllib.parse import quote, urlparse

import requests

from ...domain.ports.analytics import AnalyticsPort, ArticlePerformance
from ...shared.retry import retry

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_QUERY_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"

#: Search Console a 1 à 2 jours de latence : on ne demande jamais les données
#: les plus récentes, elles seraient incomplètes.
_REPORTING_LAG_DAYS = 2

#: Segments de chemin qui ne sont pas des slugs d'article (page d'accueil du
#: blog, pagination…) — leurs stats agrégées polluerait le signal par article.
_NON_ARTICLE_SEGMENTS = {"", "blog", "articles"}


class SearchConsoleAnalytics(AnalyticsPort):
    """Implémentation `AnalyticsPort` branchée sur la Search Console réelle."""

    name = "search-console"

    def __init__(
        self,
        *,
        site_url: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        timeout_s: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.site_url = site_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.timeout_s = timeout_s
        self._session = session or requests.Session()
        self._access_token: str | None = None
        self._token_expiry = 0.0

    def is_available(self) -> bool:
        return bool(self.site_url and self.client_id and self.client_secret and self.refresh_token)

    # ------------------------------------------------------------------ #
    def fetch_performance(self, *, days: int = 28) -> list[ArticlePerformance]:
        if not self.is_available():
            logger.info("Search Console non configuré : aucune donnée de performance")
            return []
        try:
            rows = self._query(days)
        except Exception as exc:  # noqa: BLE001 - une panne Search Console n'arrête jamais le run
            logger.warning("Search Console indisponible : %s", exc)
            return []

        performances = self._to_performances(rows)
        logger.info(
            "Search Console : %s article(s) avec des données sur les %s derniers jours",
            len(performances), days,
        )
        return performances

    # ------------------------------------------------------------------ #
    # OAuth
    # ------------------------------------------------------------------ #
    def _access_token_value(self) -> str:
        if self._access_token and time.monotonic() < self._token_expiry:
            return self._access_token

        response = self._session.post(
            _TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=self.timeout_s,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Rafraîchissement du token OAuth refusé (HTTP {response.status_code}) : "
                f"{response.text[:200]}"
            )
        data = response.json()
        self._access_token = data["access_token"]
        # Marge de 60s pour ne jamais utiliser un token expiré pile au moment de l'appel.
        self._token_expiry = time.monotonic() + int(data.get("expires_in", 3600)) - 60
        return self._access_token

    # ------------------------------------------------------------------ #
    # API Search Console
    # ------------------------------------------------------------------ #
    @retry(attempts=2, base_delay=1.5, exceptions=(requests.RequestException, RuntimeError))
    def _query(self, days: int) -> list[dict]:
        end = date.today() - timedelta(days=_REPORTING_LAG_DAYS)
        start = end - timedelta(days=days)
        url = _QUERY_URL.format(site=quote(self.site_url, safe=""))

        try:
            response = self._session.post(
                url,
                headers={"Authorization": f"Bearer {self._access_token_value()}"},
                json={
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "dimensions": ["page", "query"],
                    "rowLimit": 5000,
                },
                timeout=self.timeout_s,
            )
        except requests.RequestException as exc:
            raise requests.RequestException(f"Search Console injoignable : {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(f"Search Console HTTP {response.status_code} : {response.text[:200]}")
        return response.json().get("rows", [])

    # ------------------------------------------------------------------ #
    # Mapping requêtes → ArticlePerformance
    # ------------------------------------------------------------------ #
    def _to_performances(self, rows: list[dict]) -> list[ArticlePerformance]:
        by_slug: dict[str, dict] = {}
        for row in rows:
            keys = row.get("keys") or []
            if len(keys) < 2:
                continue
            page_url, query = keys[0], keys[1]
            slug = self._slug_from_url(page_url)
            if not slug:
                continue

            bucket = by_slug.setdefault(
                slug, {"impressions": 0, "clicks": 0, "position_weighted": 0.0, "queries": []}
            )
            impressions = int(row.get("impressions", 0))
            bucket["impressions"] += impressions
            bucket["clicks"] += int(row.get("clicks", 0))
            bucket["position_weighted"] += float(row.get("position", 0.0)) * impressions
            bucket["queries"].append((query, impressions))

        performances = []
        for slug, bucket in by_slug.items():
            impressions = bucket["impressions"]
            average_position = (bucket["position_weighted"] / impressions) if impressions else 0.0
            top_queries = tuple(
                q for q, _ in sorted(bucket["queries"], key=lambda item: item[1], reverse=True)[:5]
            )
            performances.append(ArticlePerformance(
                slug=slug,
                impressions=impressions,
                clicks=bucket["clicks"],
                average_position=round(average_position, 1),
                top_queries=top_queries,
            ))
        return performances

    @staticmethod
    def _slug_from_url(page_url: str) -> str:
        path = urlparse(page_url).path.strip("/")
        segment = path.rsplit("/", 1)[-1] if path else ""
        return "" if segment in _NON_ARTICLE_SEGMENTS else segment
