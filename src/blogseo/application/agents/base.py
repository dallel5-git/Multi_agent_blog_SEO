"""Classe de base de tous les agents.

Un agent est une unité de travail qui :
1. lit `PipelineState`,
2. fait son travail (appels LLM et/ou outils via les ports),
3. écrit son résultat dans `PipelineState`,
4. renvoie l'état.

Contrat volontairement minimal : ajouter un agent = créer une sous-classe et
l'insérer dans la liste de l'orchestrateur. Aucun agent n'en connaît un autre.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..dto.pipeline_state import PipelineState


class Agent(ABC):
    """Interface commune des 9 agents."""

    #: Identifiant technique, utilisé comme nom de nœud dans le graphe.
    name: str = "agent"
    #: Libellé lisible affiché dans les logs et les notifications.
    label: str = "Agent"
    #: Si True, une exception de cet agent fait échouer tout le run.
    critical: bool = True

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"blogseo.agents.{self.name}")

    @abstractmethod
    def run(self, state: PipelineState) -> PipelineState:
        """Exécute l'agent et renvoie l'état enrichi."""

    # ------------------------------------------------------------------ #
    def __call__(self, state: PipelineState) -> PipelineState:
        """Enveloppe l'exécution : trace, chronomètre et gestion d'erreur."""
        trace = state.run.start_step(self.name)
        self.logger.info("▶ %s", self.label)
        try:
            state = self.run(state)
        except Exception as exc:  # noqa: BLE001 - on trace puis on décide
            state.run.end_step(trace, ok=False, detail=f"{type(exc).__name__}: {exc}")
            self.logger.error("✖ %s a échoué : %s", self.label, exc, exc_info=True)
            if self.critical:
                raise
            state.warn(f"{self.label} : {exc}")
            return state

        state.run.end_step(trace, ok=True, detail=self.describe(state))
        self.logger.info("✔ %s (%.1fs) — %s", self.label, trace.duration_s, self.describe(state))
        return state

    def describe(self, state: PipelineState) -> str:
        """Résumé d'une ligne de ce que l'agent a produit (affiché dans les logs)."""
        return "terminé"
