"""Préparation des données du tableau de bord — fonctions PURES, sans aucun
`import streamlit`.

Séparé volontairement des vues (`dashboard/views/*.py`) : Streamlit ne peut
s'exécuter que dans un vrai process `streamlit run`, ce qui rendrait ce
module intestable par `pytest`. Ici, tout est du Python ordinaire qui prend
un `CalendarRepository` et renvoie des structures simples — les vues ne font
plus qu'appeler ces fonctions puis dessiner le résultat.

Lecture seule, sans exception : aucune fonction d'ici n'écrit jamais dans le
calendrier partagé, et une base vide doit produire des structures vides,
jamais lever.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..brand_kernel.schema import BrandKernel
from ..platforms import Platform
from ..shared_calendar.models import ContentItem, ContentStatus, StatSnapshot, StatSource
from ..shared_calendar.repository import CalendarRepository

# --------------------------------------------------------------------------- #
# Kanban (issue #78)
# --------------------------------------------------------------------------- #
KanbanBoard = dict[Platform, dict[ContentStatus, list[ContentItem]]]


def kanban_board(repository: CalendarRepository) -> KanbanBoard:
    """`{plateforme: {statut: [ContentItem, ...]}}` pour les 6 plateformes
    pilotées — les colonnes correspondent exactement à `ContentStatus`."""
    board: KanbanBoard = {
        platform: {status: [] for status in ContentStatus} for platform in Platform.piloted()
    }
    for platform in Platform.piloted():
        for item in repository.list_by_platform(platform):
            board[platform][item.status].append(item)
    return board


def kanban_counts(board: KanbanBoard) -> dict[ContentStatus, int]:
    """Nombre total d'éléments par colonne, toutes plateformes confondues."""
    counts = dict.fromkeys(ContentStatus, 0)
    for par_statut in board.values():
        for status, items in par_statut.items():
            counts[status] += len(items)
    return counts


# --------------------------------------------------------------------------- #
# Statistiques dans le temps (issue #79)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class StatsSeries:
    """L'historique complet des mesures d'une plateforme, prêt à tracer."""

    platform: Platform
    snapshots: tuple[StatSnapshot, ...]

    @property
    def has_data(self) -> bool:
        return bool(self.snapshots)

    @property
    def has_manual_data(self) -> bool:
        return any(snapshot.source is StatSource.MANUAL for snapshot in self.snapshots)

    @property
    def has_api_data(self) -> bool:
        return any(snapshot.source is StatSource.API for snapshot in self.snapshots)


def stats_series_by_platform(
    repository: CalendarRepository, *, since: str | None = None
) -> dict[Platform, StatsSeries]:
    """Une série par plateforme pilotée. `since` filtre sur `captured_at`
    (comparaison lexicographique, cohérente avec le format ISO du schéma)."""
    series = {}
    for platform in Platform.piloted():
        snapshots = repository.list_snapshots(platform)
        if since:
            snapshots = [s for s in snapshots if (s.captured_at or "") >= since]
        series[platform] = StatsSeries(platform=platform, snapshots=tuple(snapshots))
    return series


# --------------------------------------------------------------------------- #
# Conversions (issue #80)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ConversionSummary:
    platform: Platform
    affiliate_clicks: int
    sales: int
    revenue_tnd: float


def conversions_by_platform(repository: CalendarRepository) -> list[ConversionSummary]:
    """Ventilation par plateforme d'ORIGINE — CADRAGE.md risque n°6 : ces
    chiffres ne valent que ce que le paramètre de suivi des liens (Brand
    Kernel) a permis de rattacher, voir `tracking_caveat()`."""
    resultats = []
    for platform in Platform.piloted():
        snapshots = repository.list_snapshots(platform)
        resultats.append(
            ConversionSummary(
                platform=platform,
                affiliate_clicks=sum(s.affiliate_clicks or 0 for s in snapshots),
                sales=sum(s.sales or 0 for s in snapshots),
                revenue_tnd=sum(s.revenue_tnd or 0 for s in snapshots),
            )
        )
    return resultats


def tracking_caveat(kernel: BrandKernel | None) -> str | None:
    """Message à afficher AU LIEU de zéros silencieux (critère d'acceptation
    de l'issue #80) : soit le suivi n'est pas configuré, soit il l'est mais
    aucun collecteur automatique de clics n'existe encore dans ce projet —
    dans les deux cas, un zéro ne doit jamais être lu comme « aucune
    conversion », mais comme « rien d'enregistré pour l'instant »."""
    if kernel is None or not (kernel.tracking.param and kernel.tracking.scheme):
        return (
            "Aucun paramètre de suivi des liens n'est configuré dans le Brand Kernel "
            "(CADRAGE.md décision 6) : ces chiffres ne peuvent pas être ventilés par "
            "plateforme d'origine."
        )
    return (
        f"Suivi configuré (paramètre `{kernel.tracking.param}`, gabarit "
        f"`{kernel.tracking.scheme}`), mais aucun collecteur automatique de clics "
        "n'existe encore : ces chiffres ne reflètent que ce qui a été saisi à la main."
    )
