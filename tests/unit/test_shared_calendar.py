"""Tests du Lot 2 : migration, entités, repository, configuration, pont blog.

Toutes les bases de test sont en mémoire (`":memory:"`), jamais un fichier
temporaire — le `CalendarRepository` garde une connexion unique ouverte pour
toute sa durée de vie, ce qui rend `:memory:` utilisable en test (une
nouvelle connexion SQLite à `:memory:` verrait une base vide).
"""

from __future__ import annotations

import sqlite3

import pytest

from pilotage.config.settings import PilotageSettings
from pilotage.platforms import Platform
from pilotage.shared_calendar.blog_bridge import sync_blog_articles
from pilotage.shared_calendar.migrate import SCHEMA_SQL_PATH, apply_schema
from pilotage.shared_calendar.models import (
    ContentItem,
    ContentStatus,
    CrossRefState,
    PlatformPost,
    StatSnapshot,
)
from pilotage.shared_calendar.repository import CalendarRepository


# --------------------------------------------------------------------------- #
# migrate.apply_schema
# --------------------------------------------------------------------------- #
def test_apply_schema_cree_le_dossier_parent_et_les_tables(tmp_path):
    db_path = tmp_path / "sous_dossier" / "calendar.db"

    apply_schema(db_path)

    assert db_path.exists()
    connexion = sqlite3.connect(db_path)
    tables = {row[0] for row in connexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connexion.close()
    assert {"content_items", "platform_posts", "stat_snapshots"} <= tables


def test_apply_schema_est_rejouable(tmp_path):
    db_path = tmp_path / "calendar.db"
    apply_schema(db_path)
    apply_schema(db_path)  # ne doit pas lever


# --------------------------------------------------------------------------- #
# ContentStatus ↔ contrainte CHECK de content_items.status
# --------------------------------------------------------------------------- #
@pytest.fixture
def db() -> sqlite3.Connection:
    connexion = sqlite3.connect(":memory:")
    connexion.executescript(SCHEMA_SQL_PATH.read_text(encoding="utf-8"))
    connexion.execute("PRAGMA foreign_keys = ON")
    return connexion


@pytest.mark.parametrize("status", list(ContentStatus), ids=lambda s: s.value)
def test_toutes_les_valeurs_de_contentstatus_sont_acceptees_par_le_schema(
    db: sqlite3.Connection, status: ContentStatus
):
    db.execute(
        "INSERT INTO content_items (platform, title, status) VALUES ('youtube', 'T', ?)",
        (status.value,),
    )


def test_le_schema_ne_connait_pas_de_statut_hors_contentstatus(db: sqlite3.Connection):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO content_items (platform, title, status) VALUES ('youtube', 'T', 'archive')"
        )


# --------------------------------------------------------------------------- #
# CalendarRepository — content_items
# --------------------------------------------------------------------------- #
@pytest.fixture
def repository() -> CalendarRepository:
    repo = CalendarRepository(":memory:")
    repo._connection.executescript(SCHEMA_SQL_PATH.read_text(encoding="utf-8"))
    yield repo
    repo.close()


def test_add_item_puis_list_by_platform(repository: CalendarRepository):
    item_id = repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="Mon sujet"))

    items = repository.list_by_platform(Platform.YOUTUBE)

    assert len(items) == 1
    assert items[0].id == item_id
    assert items[0].title == "Mon sujet"
    assert items[0].status is ContentStatus.IDEA
    assert repository.list_by_platform(Platform.TIKTOK) == []


def test_update_status(repository: CalendarRepository):
    item_id = repository.add_item(ContentItem(platform=Platform.X, title="T"))

    repository.update_status(item_id, ContentStatus.PENDING_REVIEW)

    items = repository.list_by_platform(Platform.X)
    assert items[0].status is ContentStatus.PENDING_REVIEW


def test_list_pending_ne_renvoie_que_les_contenus_en_attente(repository: CalendarRepository):
    idee = repository.add_item(ContentItem(platform=Platform.X, title="idée"))
    a_valider = repository.add_item(ContentItem(platform=Platform.TIKTOK, title="à valider"))
    repository.update_status(a_valider, ContentStatus.PENDING_REVIEW)

    en_attente = repository.list_pending()

    assert [item.id for item in en_attente] == [a_valider]
    assert idee not in [item.id for item in en_attente]


# --------------------------------------------------------------------------- #
# CalendarRepository — platform_posts
# --------------------------------------------------------------------------- #
def test_add_post_puis_list_recent_posts(repository: CalendarRepository):
    item_id = repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))

    post_id = repository.add_post(
        PlatformPost(
            content_item_id=item_id,
            platform=Platform.YOUTUBE,
            url="https://youtu.be/abc",
            published_at="2026-08-25",
        )
    )

    posts = repository.list_recent_posts()
    assert len(posts) == 1
    assert posts[0].id == post_id
    assert posts[0].url == "https://youtu.be/abc"


def test_find_post_by_url(repository: CalendarRepository):
    item_id = repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    repository.add_post(
        PlatformPost(
            content_item_id=item_id,
            platform=Platform.YOUTUBE,
            url="https://youtu.be/abc",
            published_at="2026-08-25",
        )
    )

    assert repository.find_post_by_url("https://youtu.be/abc") is not None
    assert repository.find_post_by_url("https://youtu.be/inconnu") is None


# --------------------------------------------------------------------------- #
# CalendarRepository — stat_snapshots
# --------------------------------------------------------------------------- #
def test_add_snapshot_puis_latest_snapshot_renvoie_la_mesure_la_plus_recente(
    repository: CalendarRepository,
):
    item_id = repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    post_id = repository.add_post(
        PlatformPost(
            content_item_id=item_id,
            platform=Platform.YOUTUBE,
            url="https://youtu.be/abc",
            published_at="2026-08-20",
        )
    )
    # `captured_at` explicite : le défaut `datetime('now')` a une résolution à
    # la seconde, insuffisant pour distinguer trois insertions dans la même
    # boucle (voir `v_latest_stats`, qui regroupe par `captured_at`).
    for jour, vues in (("2026-08-21", 100), ("2026-08-22", 250), ("2026-08-23", 400)):
        repository.add_snapshot(
            StatSnapshot(
                platform=Platform.YOUTUBE,
                platform_post_id=post_id,
                captured_at=jour,
                views=vues,
            )
        )

    dernier = repository.latest_snapshot(post_id)

    assert dernier is not None
    assert dernier.views == 400


def test_latest_snapshot_renvoie_none_sans_mesure(repository: CalendarRepository):
    assert repository.latest_snapshot(999) is None


# --------------------------------------------------------------------------- #
# CalendarRepository — suggest_cross_reference
# --------------------------------------------------------------------------- #
def test_suggest_cross_reference_propose_un_contenu_publie_dune_autre_plateforme(
    repository: CalendarRepository,
):
    blog_id = repository.add_item(ContentItem(platform=Platform.BLOG, title="Article blog"))
    repository.update_status(blog_id, ContentStatus.PUBLISHED)
    youtube_id = repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="Vidéo"))

    candidat = repository.suggest_cross_reference(youtube_id)

    assert candidat is not None
    assert candidat.id == blog_id
    item = repository.list_by_platform(Platform.YOUTUBE)[0]
    assert item.cross_ref_id == blog_id
    assert item.cross_ref_state is CrossRefState.SUGGESTED  # jamais ACCEPTED


def test_suggest_cross_reference_ne_propose_rien_de_la_meme_plateforme(
    repository: CalendarRepository,
):
    autre_youtube = repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="Autre vidéo"))
    repository.update_status(autre_youtube, ContentStatus.PUBLISHED)
    item_id = repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="Vidéo"))

    assert repository.suggest_cross_reference(item_id) is None


def test_suggest_cross_reference_najamais_ecrase_une_mention_existante(
    repository: CalendarRepository,
):
    blog_id = repository.add_item(ContentItem(platform=Platform.BLOG, title="Article"))
    repository.update_status(blog_id, ContentStatus.PUBLISHED)
    tiktok_id = repository.add_item(ContentItem(platform=Platform.TIKTOK, title="Vidéo courte"))
    repository.suggest_cross_reference(tiktok_id)

    nouveau_blog_id = repository.add_item(ContentItem(platform=Platform.BLOG, title="Article 2"))
    repository.update_status(nouveau_blog_id, ContentStatus.PUBLISHED)
    resultat = repository.suggest_cross_reference(tiktok_id)

    assert resultat is None
    item = repository.list_by_platform(Platform.TIKTOK)[0]
    assert item.cross_ref_id == blog_id  # inchangé


# --------------------------------------------------------------------------- #
# PilotageSettings.from_env()
# --------------------------------------------------------------------------- #
_PLATFORM_ENV_KEYS = [
    f"PILOTAGE_{p.value.upper()}_{suffix}"
    for p in Platform.piloted()
    for suffix in ("BOT_TOKEN", "CHAT_ID")
]
_OTHER_ENV_KEYS = [
    "PILOTAGE_DB_PATH", "BLOG_CONTENT_DIR", "YOUTUBE_API_KEY", "YOUTUBE_CHANNEL_ID",
    "META_PAGE_ACCESS_TOKEN", "META_PAGE_ID", "META_INSTAGRAM_BUSINESS_ID",
    "TELEGRAM_CHANNEL_USERNAME", "DASHBOARD_PORT",
]


def _clean_env(monkeypatch):
    import pilotage.config.settings as settings_module

    monkeypatch.setattr(settings_module, "_load_dotenv", lambda: None)
    for key in [*_PLATFORM_ENV_KEYS, *_OTHER_ENV_KEYS]:
        monkeypatch.delenv(key, raising=False)


def test_from_env_sans_rien_de_configure(monkeypatch):
    _clean_env(monkeypatch)

    settings = PilotageSettings.from_env()

    assert settings.bots.configured_platforms == ()
    assert settings.youtube.is_configured is False
    assert settings.meta.is_configured is False
    assert settings.dashboard.port == 8501


def test_un_token_manquant_ne_desactive_que_son_bot(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("PILOTAGE_YOUTUBE_BOT_TOKEN", "token-yt")
    monkeypatch.setenv("PILOTAGE_YOUTUBE_CHAT_ID", "123")

    settings = PilotageSettings.from_env()

    assert settings.bots.configured_platforms == (Platform.YOUTUBE,)
    assert settings.bots.for_platform(Platform.TIKTOK).is_configured is False
    # from_env() ne lève pas malgré les cinq autres bots non configurés


def test_describe_ne_divulgue_aucun_secret(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("PILOTAGE_YOUTUBE_BOT_TOKEN", "secret-token-tres-prive")
    monkeypatch.setenv("PILOTAGE_YOUTUBE_CHAT_ID", "123456")
    monkeypatch.setenv("YOUTUBE_API_KEY", "AIzaSuperSecrete")

    settings = PilotageSettings.from_env()
    resume = settings.describe()

    assert "secret-token-tres-prive" not in resume
    assert "123456" not in resume
    assert "AIzaSuperSecrete" not in resume
    assert "✅ configurée" in resume


# --------------------------------------------------------------------------- #
# blog_bridge.sync_blog_articles
# --------------------------------------------------------------------------- #
_ARTICLE_MDX = """---
title: "Mon article de test"
description: "Une description courte"
date: "2026-08-20"
category: "n8n"
---

Contenu de l'article.
"""


def test_sync_blog_articles_insere_un_content_item_et_un_platform_post(tmp_path, repository):
    content_dir = tmp_path / "articles"
    content_dir.mkdir()
    (content_dir / "mon-article.mdx").write_text(_ARTICLE_MDX, encoding="utf-8")

    inserted = sync_blog_articles(repository, content_dir, "https://oussama-ai-blog-v1.vercel.app")

    assert inserted == 1
    items = repository.list_by_platform(Platform.BLOG)
    assert len(items) == 1
    assert items[0].title == "Mon article de test"
    assert items[0].status is ContentStatus.PUBLISHED

    post = repository.find_post_by_url("https://oussama-ai-blog-v1.vercel.app/blog/mon-article")
    assert post is not None
    assert post.external_id == "mon-article"


def test_sync_blog_articles_est_idempotent(tmp_path, repository):
    content_dir = tmp_path / "articles"
    content_dir.mkdir()
    (content_dir / "mon-article.mdx").write_text(_ARTICLE_MDX, encoding="utf-8")

    premier_appel = sync_blog_articles(repository, content_dir, "https://exemple.test")
    second_appel = sync_blog_articles(repository, content_dir, "https://exemple.test")

    assert premier_appel == 1
    assert second_appel == 0
    assert len(repository.list_by_platform(Platform.BLOG)) == 1


def test_sync_blog_articles_sans_dossier_ne_leve_pas(tmp_path, repository):
    assert sync_blog_articles(repository, tmp_path / "absent", "https://exemple.test") == 0
