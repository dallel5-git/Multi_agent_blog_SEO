"""Tests de `pilotage.dashboard.data` (Lot 6, issues #78-#80).

Volontairement séparés des vues Streamlit (non testées directement : elles
ne s'exécutent que dans un vrai `streamlit run`) — tout ce qui peut planter
ou mal calculer vit dans ce module pur, donc c'est lui qu'on teste.
"""

from __future__ import annotations

import dataclasses

from pilotage.brand_kernel.schema import Tracking
from pilotage.dashboard.data import (
    conversions_by_platform,
    kanban_board,
    kanban_counts,
    stats_series_by_platform,
    tracking_caveat,
)
from pilotage.platforms import Platform
from pilotage.shared_calendar.models import ContentItem, ContentStatus, PlatformPost, StatSnapshot, StatSource


# --------------------------------------------------------------------------- #
# kanban_board / kanban_counts
# --------------------------------------------------------------------------- #
def test_kanban_board_sur_base_vide_a_une_entree_par_plateforme_pilotee(calendar_repository):
    board = kanban_board(calendar_repository)

    assert set(board) == set(Platform.piloted())
    for par_statut in board.values():
        assert set(par_statut) == set(ContentStatus)
        assert all(items == [] for items in par_statut.values())


def test_kanban_board_range_chaque_item_dans_sa_colonne(calendar_repository):
    calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="Idée"))
    en_attente_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="En attente"))
    calendar_repository.update_status(en_attente_id, ContentStatus.PENDING_REVIEW)

    board = kanban_board(calendar_repository)

    assert len(board[Platform.YOUTUBE][ContentStatus.IDEA]) == 1
    assert len(board[Platform.YOUTUBE][ContentStatus.PENDING_REVIEW]) == 1
    assert board[Platform.TIKTOK][ContentStatus.IDEA] == []


def test_kanban_counts_totalise_toutes_plateformes_confondues(calendar_repository):
    calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="A"))
    calendar_repository.add_item(ContentItem(platform=Platform.TIKTOK, title="B"))

    counts = kanban_counts(kanban_board(calendar_repository))

    assert counts[ContentStatus.IDEA] == 2
    assert counts[ContentStatus.PUBLISHED] == 0


# --------------------------------------------------------------------------- #
# stats_series_by_platform
# --------------------------------------------------------------------------- #
def test_stats_series_sur_base_vide_na_pas_de_donnees(calendar_repository):
    series = stats_series_by_platform(calendar_repository)

    assert set(series) == set(Platform.piloted())
    assert all(not serie.has_data for serie in series.values())


def test_stats_series_distingue_source_manual_et_api(calendar_repository):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.X, title="T"))
    post_id = calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.X, url="https://x.com/a/1",
                     published_at="2026-08-25")
    )
    calendar_repository.add_snapshot(
        StatSnapshot(platform=Platform.X, platform_post_id=post_id, source=StatSource.MANUAL, views=10)
    )

    series = stats_series_by_platform(calendar_repository)

    assert series[Platform.X].has_data
    assert series[Platform.X].has_manual_data
    assert not series[Platform.X].has_api_data
    assert not series[Platform.YOUTUBE].has_data


def test_stats_series_filtre_par_since(calendar_repository):
    calendar_repository.add_snapshot(
        StatSnapshot(platform=Platform.YOUTUBE, captured_at="2026-01-01", followers=10)
    )
    calendar_repository.add_snapshot(
        StatSnapshot(platform=Platform.YOUTUBE, captured_at="2026-08-01", followers=20)
    )

    recent = stats_series_by_platform(calendar_repository, since="2026-06-01")

    assert len(recent[Platform.YOUTUBE].snapshots) == 1
    assert recent[Platform.YOUTUBE].snapshots[0].followers == 20


# --------------------------------------------------------------------------- #
# conversions_by_platform / tracking_caveat
# --------------------------------------------------------------------------- #
def test_conversions_by_platform_sur_base_vide_est_a_zero_partout(calendar_repository):
    resume = conversions_by_platform(calendar_repository)

    assert len(resume) == len(Platform.piloted())
    assert all(r.affiliate_clicks == 0 and r.sales == 0 and r.revenue_tnd == 0 for r in resume)


def test_conversions_by_platform_agrege_par_plateforme_dorigine(calendar_repository):
    calendar_repository.add_snapshot(
        StatSnapshot(platform=Platform.YOUTUBE, affiliate_clicks=3, sales=1, revenue_tnd=50.0)
    )
    calendar_repository.add_snapshot(
        StatSnapshot(platform=Platform.YOUTUBE, affiliate_clicks=2, sales=0, revenue_tnd=0.0)
    )
    calendar_repository.add_snapshot(
        StatSnapshot(platform=Platform.TIKTOK, affiliate_clicks=1, sales=0, revenue_tnd=0.0)
    )

    resume = {r.platform: r for r in conversions_by_platform(calendar_repository)}

    assert resume[Platform.YOUTUBE].affiliate_clicks == 5
    assert resume[Platform.YOUTUBE].revenue_tnd == 50.0
    assert resume[Platform.TIKTOK].affiliate_clicks == 1
    assert resume[Platform.FACEBOOK].affiliate_clicks == 0


def test_tracking_caveat_sans_brand_kernel():
    message = tracking_caveat(None)
    assert message is not None
    assert "n'est configuré" in message


def test_tracking_caveat_avec_brand_kernel_configure(brand_kernel):
    message = tracking_caveat(brand_kernel)

    assert message is not None
    assert brand_kernel.tracking.param in message
    assert "aucun collecteur automatique" in message


def test_tracking_caveat_sans_parametre_de_suivi(brand_kernel):
    kernel_sans_suivi = dataclasses.replace(
        brand_kernel, tracking=Tracking(param="", scheme="")
    )

    message = tracking_caveat(kernel_sans_suivi)

    assert message is not None
    assert "n'est configuré" in message
