"""Saisie manuelle guidée des statistiques X et TikTok (aucune API gratuite).

N'implémente PAS le port `StatsCollector` : contrairement aux adapters API,
il n'y a rien à « collecter » tout seul ici — l'humain doit répondre. C'est
délibérément un jeu de fonctions pures, appelées par les commandes `/mesure`
et `/passe` du socle commun des bots (`pilotage.bots.base.PilotageBot`),
pas un objet interrogé périodiquement.

Principe du risque n°4 de CADRAGE.md : une question à la fois, jamais un
formulaire. `/rappel_stats` (voir `PilotageBot.compose_manual_stats_reminder`,
lot 4) liste les publications sans mesure ; l'auteur répond publication par
publication, à son rythme, avec `/mesure <id> <vues> [likes]` ou passe une
publication avec `/passe <id>` sans bloquer les suivantes.
"""

from __future__ import annotations

from ..platforms import Platform
from ..shared_calendar.models import PlatformPost, StatSnapshot, StatSource
from ..shared_calendar.repository import CalendarRepository

#: Les deux seules plateformes concernées (CADRAGE.md risque n°4).
MANUAL_ENTRY_PLATFORMS = (Platform.X, Platform.TIKTOK)


def posts_needing_manual_entry(repository: CalendarRepository, platform: Platform) -> list[PlatformPost]:
    """Publications de `platform` sans mesure récente — ce que `/mesure` et
    `/passe` doivent traiter en priorité."""
    if platform not in MANUAL_ENTRY_PLATFORMS:
        return []
    return [
        post for post in repository.list_recent_posts(limit=100)
        if post.platform is platform and repository.latest_snapshot(post.id) is None
    ]


def record_manual_measurement(
    repository: CalendarRepository,
    *,
    platform_post_id: int,
    platform: Platform,
    views: int,
    likes: int | None = None,
) -> StatSnapshot:
    """Enregistre une mesure saisie à la main, `source = 'manual'` — jamais
    confondue avec une mesure d'API (CADRAGE.md risque n°4)."""
    snapshot = StatSnapshot(
        platform=platform,
        platform_post_id=platform_post_id,
        source=StatSource.MANUAL,
        views=views,
        likes=likes,
    )
    repository.add_snapshot(snapshot)
    return snapshot
