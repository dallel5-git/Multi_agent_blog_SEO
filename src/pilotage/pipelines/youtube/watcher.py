"""Veille propre à YouTube — mêmes sources que le blog (CADRAGE.md décision 11) :
Hacker News, Reddit, dev.to, RSS Tunisie. L'implémentation vit dans
`pilotage.shared.trend_sources` (partagée par les 6 pipelines, mêmes flux
pour tous) ; ce module ne fait qu'y brancher YouTube.
"""

from __future__ import annotations

from ...shared.trend_sources import collect_trends as _collect_trends
from ..base import TrendItem


def collect_trends(*, limit: int = 15, offline: bool = False) -> list[TrendItem]:
    return _collect_trends(limit=limit, offline=offline, label="YouTube")
