"""Accès aux données du calendrier partagé — seul endroit du projet où du SQL
est écrit.

`sqlite3` de la bibliothèque standard, aucun ORM. Une connexion unique est
ouverte à la construction et réutilisée pour tous les appels (plutôt qu'une
connexion par méthode) : c'est ce qui permet aux tests de tourner sur une
base `:memory:` sans fichier temporaire — une base en mémoire n'existe que le
temps d'une connexion SQLite, une nouvelle connexion en verrait une autre,
vide.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..platforms import Platform
from .models import ContentItem, ContentStatus, CrossRefState, PlatformPost, StatSnapshot, StatSource


def _row_to_content_item(row: sqlite3.Row) -> ContentItem:
    return ContentItem(
        id=row["id"],
        platform=Platform(row["platform"]),
        title=row["title"],
        topic=row["topic"],
        body=row["body"],
        status=ContentStatus(row["status"]),
        cross_ref_id=row["cross_ref_id"],
        cross_ref_state=CrossRefState(row["cross_ref_state"]),
        scheduled_for=row["scheduled_for"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_platform_post(row: sqlite3.Row) -> PlatformPost:
    return PlatformPost(
        id=row["id"],
        content_item_id=row["content_item_id"],
        platform=Platform(row["platform"]),
        url=row["url"],
        external_id=row["external_id"],
        published_at=row["published_at"],
        created_at=row["created_at"],
    )


def _row_to_stat_snapshot(row: sqlite3.Row) -> StatSnapshot:
    return StatSnapshot(
        id=row["id"],
        platform=Platform(row["platform"]),
        platform_post_id=row["platform_post_id"],
        source=StatSource(row["source"]),
        captured_at=row["captured_at"],
        views=row["views"],
        likes=row["likes"],
        comments=row["comments"],
        shares=row["shares"],
        followers=row["followers"],
        affiliate_clicks=row["affiliate_clicks"],
        sales=row["sales"],
        revenue_tnd=row["revenue_tnd"],
    )


class CalendarRepository:
    """Accès en lecture/écriture au calendrier partagé (`shared_calendar/schema.sql`)."""

    def __init__(self, db_path: Path | str) -> None:
        self._connection = sqlite3.connect(db_path)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> CalendarRepository:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ----------------------------------------------------------------- #
    # content_items
    # ----------------------------------------------------------------- #
    def add_item(self, item: ContentItem) -> int:
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO content_items
                    (platform, title, topic, body, status, scheduled_for)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.platform.value,
                    item.title,
                    item.topic,
                    item.body,
                    item.status.value,
                    item.scheduled_for,
                ),
            )
            return int(cursor.lastrowid)

    def update_status(self, item_id: int, status: ContentStatus) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE content_items SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (status.value, item_id),
            )

    def update_body(self, item_id: int, body: str) -> None:
        """Utilisé par le bouton ✏️ des bots : réécrit `body` avec le retour
        de l'auteur, sans changer le statut (`_handle_callback` s'en charge)."""
        with self._connection:
            self._connection.execute(
                "UPDATE content_items SET body = ?, updated_at = datetime('now') WHERE id = ?",
                (body, item_id),
            )

    def get_item(self, item_id: int) -> ContentItem | None:
        row = self._connection.execute(
            "SELECT * FROM content_items WHERE id = ?", (item_id,)
        ).fetchone()
        return _row_to_content_item(row) if row else None

    def list_by_platform(self, platform: Platform) -> list[ContentItem]:
        rows = self._connection.execute(
            "SELECT * FROM content_items WHERE platform = ? ORDER BY created_at DESC",
            (platform.value,),
        ).fetchall()
        return [_row_to_content_item(row) for row in rows]

    def list_pending(self) -> list[ContentItem]:
        """Contenus en attente de validation manuelle (`/en_attente` des bots)."""
        rows = self._connection.execute(
            "SELECT * FROM content_items WHERE status = ? ORDER BY created_at ASC",
            (ContentStatus.PENDING_REVIEW.value,),
        ).fetchall()
        return [_row_to_content_item(row) for row in rows]

    # ----------------------------------------------------------------- #
    # platform_posts
    # ----------------------------------------------------------------- #
    def add_post(self, post: PlatformPost) -> int:
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO platform_posts
                    (content_item_id, platform, url, external_id, published_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    post.content_item_id,
                    post.platform.value,
                    post.url,
                    post.external_id,
                    post.published_at,
                ),
            )
            return int(cursor.lastrowid)

    def list_recent_posts(self, limit: int = 10) -> list[PlatformPost]:
        rows = self._connection.execute(
            "SELECT * FROM platform_posts ORDER BY published_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_platform_post(row) for row in rows]

    def find_post_by_url(self, url: str) -> PlatformPost | None:
        """Utilisé pour les insertions idempotentes (ex. pont blog → calendrier)."""
        row = self._connection.execute(
            "SELECT * FROM platform_posts WHERE url = ?", (url,)
        ).fetchone()
        return _row_to_platform_post(row) if row else None

    # ----------------------------------------------------------------- #
    # stat_snapshots
    # ----------------------------------------------------------------- #
    def add_snapshot(self, snapshot: StatSnapshot) -> int:
        # `captured_at` n'est ajouté que s'il est fourni explicitement : la
        # colonne a `NOT NULL DEFAULT (datetime('now'))`, et insérer NULL
        # explicitement violerait la contrainte au lieu de laisser jouer le
        # défaut — il faut donc omettre la colonne, pas lui passer None.
        colonnes = [
            "platform_post_id", "platform", "source", "views", "likes", "comments",
            "shares", "followers", "affiliate_clicks", "sales", "revenue_tnd",
        ]
        valeurs: list[object] = [
            snapshot.platform_post_id,
            snapshot.platform.value,
            snapshot.source.value,
            snapshot.views,
            snapshot.likes,
            snapshot.comments,
            snapshot.shares,
            snapshot.followers,
            snapshot.affiliate_clicks,
            snapshot.sales,
            snapshot.revenue_tnd,
        ]
        if snapshot.captured_at is not None:
            colonnes.append("captured_at")
            valeurs.append(snapshot.captured_at)

        placeholders = ", ".join("?" for _ in colonnes)
        with self._connection:
            cursor = self._connection.execute(
                f"INSERT INTO stat_snapshots ({', '.join(colonnes)}) VALUES ({placeholders})",
                valeurs,
            )
            return int(cursor.lastrowid)

    def latest_snapshot(self, platform_post_id: int) -> StatSnapshot | None:
        row = self._connection.execute(
            "SELECT * FROM v_latest_stats WHERE platform_post_id = ?", (platform_post_id,)
        ).fetchone()
        return _row_to_stat_snapshot(row) if row else None

    def list_snapshots(self, platform: Platform) -> list[StatSnapshot]:
        """Historique complet des mesures de `platform`, triées par date de
        capture — utilisé pour tracer une courbe (tableau de bord, lot 6),
        pas juste la dernière valeur connue (`latest_snapshot`)."""
        rows = self._connection.execute(
            "SELECT * FROM stat_snapshots WHERE platform = ? ORDER BY captured_at ASC",
            (platform.value,),
        ).fetchall()
        return [_row_to_stat_snapshot(row) for row in rows]

    # ----------------------------------------------------------------- #
    # Mention croisée — toujours SUGGÉRÉE, jamais imposée (ARCHITECTURE.md §3)
    # ----------------------------------------------------------------- #
    def suggest_cross_reference(self, item_id: int) -> ContentItem | None:
        """Propose un contenu publié sur une AUTRE plateforme, sans rien imposer.

        N'écrit jamais `cross_ref_state = 'accepted'` — seul l'auteur accepte,
        via le bot. Ne propose rien si `item_id` a déjà une mention croisée
        (acceptée, suggérée ou déclinée) : c'est à l'auteur de la traiter
        d'abord.
        """
        item_row = self._connection.execute(
            "SELECT * FROM content_items WHERE id = ?", (item_id,)
        ).fetchone()
        if item_row is None:
            return None
        item = _row_to_content_item(item_row)
        if item.cross_ref_state is not CrossRefState.NONE:
            return None

        candidate_row = self._connection.execute(
            """
            SELECT * FROM content_items
            WHERE status = ? AND platform != ? AND id != ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (ContentStatus.PUBLISHED.value, item.platform.value, item_id),
        ).fetchone()
        if candidate_row is None:
            return None
        candidate = _row_to_content_item(candidate_row)

        with self._connection:
            self._connection.execute(
                "UPDATE content_items SET cross_ref_id = ?, cross_ref_state = ? WHERE id = ?",
                (candidate.id, CrossRefState.SUGGESTED.value, item_id),
            )
        return candidate
