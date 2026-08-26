"""Collecteurs Meta Graph API — Facebook (Page Insights) et Instagram (compte
Business), en REST brut.

⚠️ Mise en place entièrement administrative (CADRAGE.md risque n°3) : compte
Meta Business, Page Facebook, compte Instagram Business relié à la Page,
application Meta, jeton de page longue durée — qui expire au bout d'environ
60 jours. Procédure pas à pas : `docs/META_SETUP.md`.

Deux classes distinctes bien que les deux utilisent le même jeton de page :
Facebook peut tomber (jeton révoqué côté Page) sans affecter Instagram, et
inversement — chacune journalise et rend `[]` indépendamment de l'autre.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import requests

from ..platforms import Platform
from ..shared_calendar.models import StatSnapshot, StatSource
from ..shared_calendar.repository import CalendarRepository
from .base import StatsCollector

_TIMEOUT_S = 20
_GRAPH_API = "https://graph.facebook.com/v19.0"

#: Code d'erreur Meta pour un jeton expiré ou invalide (OAuthException).
_TOKEN_ERROR_CODE = 190


def _is_token_error(payload: dict) -> bool:
    return payload.get("error", {}).get("code") == _TOKEN_ERROR_CODE


def _token_error_message(context: str) -> str:
    return (
        f"Jeton Meta expiré ou invalide ({context}) — renouvelle-le "
        "(voir docs/META_SETUP.md, CADRAGE.md risque n°3)."
    )


class FacebookStatsCollector(StatsCollector):
    """Mesures de compte (followers) et de publication (Page Insights)."""

    platform = Platform.FACEBOOK

    def __init__(self, repository: CalendarRepository, *, page_access_token: str, page_id: str) -> None:
        super().__init__(repository)
        self.page_access_token = page_access_token
        self.page_id = page_id

    def collect(self, since: date) -> list[StatSnapshot]:
        if not (self.page_access_token and self.page_id):
            self.logger.info("META_PAGE_ACCESS_TOKEN / META_PAGE_ID absent(s) — collecte ignorée.")
            return []

        try:
            response = requests.get(
                f"{_GRAPH_API}/{self.page_id}",
                params={"fields": "followers_count", "access_token": self.page_access_token},
                timeout=_TIMEOUT_S,
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            self.logger.warning("Meta Graph API (Facebook) injoignable : %s", exc)
            return []

        if _is_token_error(payload):
            self.logger.warning(_token_error_message("Facebook"))
            return []
        if "error" in payload:
            self.logger.warning("Meta Graph API (Facebook) → %s", payload["error"].get("message"))
            return []

        return [
            StatSnapshot(
                platform=Platform.FACEBOOK,
                platform_post_id=None,  # mesure de compte
                source=StatSource.API,
                followers=payload.get("followers_count"),
            )
        ]


class InstagramStatsCollector(StatsCollector):
    """Mesures par publication (vues/likes/commentaires) via `/{ig-id}/media`."""

    platform = Platform.INSTAGRAM

    def __init__(
        self, repository: CalendarRepository, *, page_access_token: str, ig_business_id: str
    ) -> None:
        super().__init__(repository)
        self.page_access_token = page_access_token
        self.ig_business_id = ig_business_id

    def collect(self, since: date) -> list[StatSnapshot]:
        if not (self.page_access_token and self.ig_business_id):
            self.logger.info(
                "META_PAGE_ACCESS_TOKEN / META_INSTAGRAM_BUSINESS_ID absent(s) — collecte ignorée."
            )
            return []

        posts = {
            post.external_id: post
            for post in self.repository.list_recent_posts(limit=200)
            if post.platform is Platform.INSTAGRAM and post.external_id
        }
        if not posts:
            return []

        try:
            response = requests.get(
                f"{_GRAPH_API}/{self.ig_business_id}/media",
                params={
                    "fields": "id,like_count,comments_count",
                    "access_token": self.page_access_token,
                    "limit": 50,
                },
                timeout=_TIMEOUT_S,
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            self.logger.warning("Meta Graph API (Instagram) injoignable : %s", exc)
            return []

        if _is_token_error(payload):
            self.logger.warning(_token_error_message("Instagram"))
            return []
        if "error" in payload:
            self.logger.warning("Meta Graph API (Instagram) → %s", payload["error"].get("message"))
            return []

        snapshots = []
        for media in payload.get("data", []):
            post = posts.get(media.get("id"))
            if post is None:
                continue
            snapshots.append(
                StatSnapshot(
                    platform=Platform.INSTAGRAM,
                    platform_post_id=post.id,
                    source=StatSource.API,
                    likes=media.get("like_count"),
                    comments=media.get("comments_count"),
                )
            )
        return snapshots


# --------------------------------------------------------------------------- #
# Renouvellement du jeton — CADRAGE.md risque n°3 : « prévoir un rappel »
# --------------------------------------------------------------------------- #
def token_days_remaining(page_access_token: str, *, timeout_s: int = _TIMEOUT_S) -> int | None:
    """Interroge `/debug_token` : jours restants avant expiration, ou `None`
    si le jeton n'a pas de date d'expiration connue ou si l'appel échoue.

    Meta exige normalement un jeton d'app distinct pour `input_token` sur cet
    endpoint ; en pratique, un jeton de page peut s'auto-inspecter. Si Meta
    répond une erreur, on ne peut simplement pas répondre — `None` plutôt
    qu'une fausse alerte.
    """
    try:
        response = requests.get(
            f"{_GRAPH_API}/debug_token",
            params={"input_token": page_access_token, "access_token": page_access_token},
            timeout=timeout_s,
        )
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None

    data = payload.get("data", {})
    expires_at = data.get("expires_at")
    if not expires_at:  # 0 ou absent = jeton longue durée sans expiration connue
        return None

    expiration = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    return max(0, (expiration - datetime.now(timezone.utc)).days)


#: En dessous de ce seuil, le rappel devient pertinent.
TOKEN_RENEWAL_WARNING_DAYS = 7


def token_renewal_reminder(page_access_token: str) -> str | None:
    """Message de rappel si le jeton expire dans moins de
    `TOKEN_RENEWAL_WARNING_DAYS` jours, sinon `None`."""
    jours = token_days_remaining(page_access_token)
    if jours is None or jours > TOKEN_RENEWAL_WARNING_DAYS:
        return None
    return (
        f"⚠️ Le jeton de page Meta expire dans {jours} jour(s). "
        "Renouvelle-le via docs/META_SETUP.md avant que Facebook et Instagram "
        "ne s'arrêtent de remonter des statistiques."
    )
