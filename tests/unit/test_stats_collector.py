"""Tests du Lot 5 — Agent Collecteur de Statistiques (issues #72-#76).

Toutes les mesures réseau sont mockées via `monkeypatch.setattr(requests,
"get", ...)` : aucun vrai appel HTTP dans ces tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import requests

from pilotage.platforms import Platform
from pilotage.shared_calendar.models import ContentItem, PlatformPost, StatSnapshot, StatSource
from pilotage.stats_collector.base import StatsCollector
from pilotage.stats_collector.manual_entry import (
    MANUAL_ENTRY_PLATFORMS,
    posts_needing_manual_entry,
    record_manual_measurement,
)
from pilotage.stats_collector.meta_graph import (
    FacebookStatsCollector,
    InstagramStatsCollector,
    token_days_remaining,
    token_renewal_reminder,
)
from pilotage.stats_collector.telegram_api import TelegramChannelStatsCollector
from pilotage.stats_collector.youtube_api import YouTubeStatsCollector


class FakeResponse:
    def __init__(self, payload: dict, *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


# --------------------------------------------------------------------------- #
# StatsCollector (port) — résilience de run()
# --------------------------------------------------------------------------- #
class _CollecteurCasse(StatsCollector):
    platform = Platform.YOUTUBE

    def collect(self, since: date) -> list[StatSnapshot]:
        raise RuntimeError("panne réseau")


class _CollecteurOk(StatsCollector):
    platform = Platform.YOUTUBE

    def collect(self, since: date) -> list[StatSnapshot]:
        return [StatSnapshot(platform=Platform.YOUTUBE, views=10)]


def test_run_dun_collecteur_casse_ne_leve_pas_et_renvoie_zero(calendar_repository):
    assert _CollecteurCasse(calendar_repository).run(date.today()) == 0


def test_run_dun_collecteur_ok_persiste_les_mesures(calendar_repository):
    compte = _CollecteurOk(calendar_repository).run(date.today())

    assert compte == 1
    # Vérifié indirectement : add_snapshot a bien été appelé (aucune levée).


# --------------------------------------------------------------------------- #
# YouTubeStatsCollector
# --------------------------------------------------------------------------- #
def test_youtube_sans_cle_ne_fait_aucun_appel(calendar_repository, monkeypatch):
    appele = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: appele.append(1))

    collector = YouTubeStatsCollector(calendar_repository, api_key="")
    assert collector.collect(date.today()) == []
    assert not appele


def test_youtube_sans_publication_ne_fait_aucun_appel(calendar_repository, monkeypatch):
    appele = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: appele.append(1))

    collector = YouTubeStatsCollector(calendar_repository, api_key="clé")
    assert collector.collect(date.today()) == []
    assert not appele


def test_youtube_construit_un_snapshot_par_video(calendar_repository, monkeypatch):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    post_id = calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.YOUTUBE, url="https://youtu.be/abc",
                     external_id="abc", published_at="2026-08-25")
    )

    def fake_get(url, params=None, timeout=None):
        return FakeResponse({"items": [
            {"id": "abc", "statistics": {"viewCount": "100", "likeCount": "10", "commentCount": "2"}}
        ]})

    monkeypatch.setattr(requests, "get", fake_get)
    collector = YouTubeStatsCollector(calendar_repository, api_key="clé")

    snapshots = collector.collect(date.today())

    assert len(snapshots) == 1
    assert snapshots[0].platform_post_id == post_id
    assert snapshots[0].views == 100
    assert snapshots[0].source is StatSource.API


def test_youtube_403_quota_epuise_renvoie_liste_vide(calendar_repository, monkeypatch):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.YOUTUBE, url="https://youtu.be/abc",
                     external_id="abc", published_at="2026-08-25")
    )
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({}, status_code=403))

    collector = YouTubeStatsCollector(calendar_repository, api_key="clé")
    assert collector.collect(date.today()) == []


def test_youtube_panne_reseau_renvoie_liste_vide(calendar_repository, monkeypatch):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.YOUTUBE, url="https://youtu.be/abc",
                     external_id="abc", published_at="2026-08-25")
    )

    def leve(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", leve)
    collector = YouTubeStatsCollector(calendar_repository, api_key="clé")
    assert collector.collect(date.today()) == []


# --------------------------------------------------------------------------- #
# FacebookStatsCollector / InstagramStatsCollector
# --------------------------------------------------------------------------- #
def test_facebook_sans_identifiants_ne_fait_aucun_appel(calendar_repository, monkeypatch):
    appele = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: appele.append(1))

    collector = FacebookStatsCollector(calendar_repository, page_access_token="", page_id="")
    assert collector.collect(date.today()) == []
    assert not appele


def test_facebook_construit_une_mesure_de_compte(calendar_repository, monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse({"followers_count": 42})
    )
    collector = FacebookStatsCollector(calendar_repository, page_access_token="t", page_id="1")

    snapshots = collector.collect(date.today())

    assert len(snapshots) == 1
    assert snapshots[0].platform_post_id is None  # mesure de compte
    assert snapshots[0].followers == 42


def test_facebook_jeton_expire_produit_un_message_actionnable_pas_une_exception(
    calendar_repository, monkeypatch, caplog
):
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse({"error": {"code": 190, "message": "Token expired"}}),
    )
    collector = FacebookStatsCollector(calendar_repository, page_access_token="t", page_id="1")

    with caplog.at_level("WARNING"):
        snapshots = collector.collect(date.today())  # ne doit pas lever

    assert snapshots == []
    assert any("renouvelle" in message.lower() for message in caplog.messages)


def test_instagram_construit_un_snapshot_par_media(calendar_repository, monkeypatch):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.INSTAGRAM, title="T"))
    post_id = calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.INSTAGRAM,
                     url="https://instagram.com/p/abc", external_id="media123",
                     published_at="2026-08-25")
    )
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse({"data": [{"id": "media123", "like_count": 5, "comments_count": 1}]}),
    )
    collector = InstagramStatsCollector(calendar_repository, page_access_token="t", ig_business_id="1")

    snapshots = collector.collect(date.today())

    assert len(snapshots) == 1
    assert snapshots[0].platform_post_id == post_id
    assert snapshots[0].likes == 5


def test_token_days_remaining_calcule_les_jours_restants(monkeypatch):
    expiration = datetime.now(UTC) + timedelta(days=5)
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse({"data": {"expires_at": int(expiration.timestamp())}}),
    )
    assert token_days_remaining("t") in (4, 5)  # arrondi, tolérance d'une journée


def test_token_days_remaining_none_sans_expiration_connue(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"data": {}}))
    assert token_days_remaining("t") is None


def test_token_renewal_reminder_silencieux_si_encore_loin(monkeypatch):
    expiration = datetime.now(UTC) + timedelta(days=30)
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse({"data": {"expires_at": int(expiration.timestamp())}}),
    )
    assert token_renewal_reminder("t") is None


def test_token_renewal_reminder_alerte_si_proche(monkeypatch):
    expiration = datetime.now(UTC) + timedelta(days=2)
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse({"data": {"expires_at": int(expiration.timestamp())}}),
    )
    message = token_renewal_reminder("t")
    assert message is not None
    assert "expire" in message.lower()


# --------------------------------------------------------------------------- #
# TelegramChannelStatsCollector
# --------------------------------------------------------------------------- #
def test_telegram_channel_construit_une_mesure_dabonnes(calendar_repository, monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse({"ok": True, "result": 1234})
    )
    collector = TelegramChannelStatsCollector(
        calendar_repository, bot_token="t", channel_username="@moncanal"
    )

    snapshots = collector.collect(date.today())

    assert len(snapshots) == 1
    assert snapshots[0].followers == 1234
    assert snapshots[0].platform_post_id is None


def test_telegram_channel_detecte_labsence_de_droits_admin(calendar_repository, monkeypatch, caplog):
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse(
            {"ok": False, "description": "Bad Request: user is not an administrator"}
        ),
    )
    collector = TelegramChannelStatsCollector(
        calendar_repository, bot_token="t", channel_username="@moncanal"
    )

    with caplog.at_level("WARNING"):
        snapshots = collector.collect(date.today())

    assert snapshots == []
    assert any("administrateur" in message.lower() for message in caplog.messages)


# --------------------------------------------------------------------------- #
# manual_entry — saisie guidée X / TikTok (issue #76)
# --------------------------------------------------------------------------- #
def test_manual_entry_platforms_est_limite_a_x_et_tiktok():
    assert set(MANUAL_ENTRY_PLATFORMS) == {Platform.X, Platform.TIKTOK}


def test_posts_needing_manual_entry_ignore_les_autres_plateformes(calendar_repository):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.YOUTUBE, url="https://youtu.be/x",
                     published_at="2026-08-25")
    )
    assert posts_needing_manual_entry(calendar_repository, Platform.YOUTUBE) == []


def test_posts_needing_manual_entry_liste_les_posts_sans_mesure(calendar_repository):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.X, title="T"))
    post_id = calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.X, url="https://x.com/a/status/1",
                     published_at="2026-08-25")
    )

    en_attente = posts_needing_manual_entry(calendar_repository, Platform.X)
    assert [p.id for p in en_attente] == [post_id]

    record_manual_measurement(
        calendar_repository, platform_post_id=post_id, platform=Platform.X, views=10
    )
    assert posts_needing_manual_entry(calendar_repository, Platform.X) == []


def test_record_manual_measurement_utilise_la_source_manual(calendar_repository):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.TIKTOK, title="T"))
    post_id = calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.TIKTOK,
                     url="https://tiktok.com/@a/video/1", published_at="2026-08-25")
    )

    snapshot = record_manual_measurement(
        calendar_repository, platform_post_id=post_id, platform=Platform.TIKTOK, views=99, likes=3
    )

    assert snapshot.source is StatSource.MANUAL
    releve = calendar_repository.latest_snapshot(post_id)
    assert releve is not None
    assert releve.views == 99
