"""Contrat commun des collecteurs de statistiques.

`collect()` est le seul point d'extension : ajouter une plateforme, c'est
ajouter un adapter qui l'implémente, rien d'autre à modifier. `run()`
enveloppe l'appel et garantit le contrat de résilience du lot — un
collecteur en panne journalise et rend une liste vide, il ne fait jamais
échouer les autres (même filet de sécurité que `PlatformPipeline._safe_watch()`
au lot 3 : chaque adapter est censé déjà gérer ses propres pannes réseau,
`run()` n'est qu'un dernier rattrapage défensif).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date

from ..platforms import Platform
from ..shared_calendar.models import StatSnapshot
from ..shared_calendar.repository import CalendarRepository


class StatsCollector(ABC):
    """Port commun : `collect()` renvoie des mesures, ne les persiste jamais
    elle-même (`run()` s'en charge) — plus facile à tester en isolation."""

    platform: Platform

    def __init__(self, repository: CalendarRepository) -> None:
        self.repository = repository
        self.logger = logging.getLogger(f"pilotage.stats_collector.{self.platform.value}")

    @abstractmethod
    def collect(self, since: date) -> list[StatSnapshot]:
        """Collecte les mesures depuis `since`. Ne doit jamais lever : une
        panne réseau ou API se journalise et renvoie `[]`."""

    def run(self, since: date) -> int:
        """Collecte puis persiste via `CalendarRepository.add_snapshot`.
        Renvoie le nombre de mesures enregistrées."""
        try:
            snapshots = self.collect(since)
        except Exception as exc:  # noqa: BLE001 - filet défensif, voir docstring du module
            self.logger.warning(
                "Collecte %s indisponible : %s", self.platform.value, exc, exc_info=True
            )
            return 0

        for snapshot in snapshots:
            self.repository.add_snapshot(snapshot)
        return len(snapshots)
