"""Exécuteur séquentiel : implémentation de référence, sans dépendance externe.

Parcourt le graphe décrit dans `pipeline_spec` avec une simple boucle. Utilisé :
- quand `ORCHESTRATOR=sequential` ;
- automatiquement en repli si LangGraph n'est pas installé ;
- dans les tests, car il est totalement déterministe et facile à instrumenter.
"""

from __future__ import annotations

import logging

from ..application.dto.pipeline_state import PipelineState
from ..domain.entities.pipeline_run import RunStatus
from .pipeline_spec import END, ENTRY_POINT, LINEAR_EDGES, ROUTES, AgentBundle

logger = logging.getLogger(__name__)

#: Garde-fou anti-boucle infinie.
MAX_NODE_VISITS = 40


class SequentialOrchestrator:
    """Exécute le pipeline nœud par nœud."""

    name = "sequential"

    def __init__(self, agents: AgentBundle, *, max_revisions: int = 2) -> None:
        self.agents = agents
        self.max_revisions = max_revisions
        self._nodes = agents.by_name()

    def run(self, state: PipelineState) -> PipelineState:
        current = ENTRY_POINT
        visits = 0

        while current != END:
            visits += 1
            if visits > MAX_NODE_VISITS:
                state.warn(f"Arrêt de sécurité : plus de {MAX_NODE_VISITS} transitions")
                logger.error("Boucle détectée dans le pipeline — arrêt forcé")
                break

            agent = self._nodes.get(current)
            if agent is None:
                logger.error("Nœud inconnu dans le graphe : %s", current)
                break

            state = agent(state)
            current = self._next_node(current, state)

        if state.run.status is RunStatus.RUNNING:
            state.run.finish(RunStatus.FAILED)
        return state

    def _next_node(self, current: str, state: PipelineState) -> str:
        router = ROUTES.get(current)
        if router is not None:
            target = router(state, self.max_revisions)
            logger.debug("Routage %s → %s", current, target)
            return target
        return LINEAR_EDGES.get(current, END)
