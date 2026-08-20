"""Exécuteur LangGraph : le graphe d'états des 9 agents.

LangGraph apporte ici trois choses concrètes par rapport à une boucle Python :
1. les **boucles conditionnelles** (Quality Gate → Content Writer, bouton 🔁 →
   Content Writer) sont déclarées, pas codées en dur ;
2. le graphe est **inspectable** (`describe()` produit un diagramme Mermaid) ;
3. il ouvrira la porte aux checkpoints et à l'exécution partielle.

L'état circulant dans le graphe est enveloppé dans un dictionnaire à une seule
clé (`{"state": PipelineState}`) : c'est le moyen le plus simple de garder nos
entités typées sans écrire un `TypedDict` par champ.

Si `langgraph` n'est pas installé, l'orchestrateur séquentiel prend le relais
automatiquement — le pipeline reste 100 % fonctionnel.
"""

from __future__ import annotations

import logging
from typing import Any

from ..application.dto.pipeline_state import PipelineState
from ..domain.entities.pipeline_run import RunStatus
from .pipeline_spec import END, ENTRY_POINT, LINEAR_EDGES, ROUTES, AgentBundle
from .sequential import SequentialOrchestrator

logger = logging.getLogger(__name__)


def langgraph_available() -> bool:
    try:
        import langgraph  # type: ignore[import-not-found]  # noqa: F401

        return True
    except ImportError:
        return False


class LangGraphOrchestrator:
    """Compile et exécute le pipeline sous forme de graphe LangGraph."""

    name = "langgraph"

    def __init__(self, agents: AgentBundle, *, max_revisions: int = 2, recursion_limit: int = 40) -> None:
        self.agents = agents
        self.max_revisions = max_revisions
        self.recursion_limit = recursion_limit
        self._compiled = self._build()

    # ------------------------------------------------------------------ #
    def _build(self):
        from typing import TypedDict

        from langgraph.graph import END as LG_END  # type: ignore[import-not-found]
        from langgraph.graph import StateGraph

        class GraphState(TypedDict):
            """Schéma d'état du graphe : une seule clé, notre `PipelineState`.

            Un TypedDict (et non `dict`) est indispensable : il donne à LangGraph
            un canal nommé par clé. Avec `dict`, tout passe par un canal racine
            `__root__` en LastValue, qui refuse deux écritures dans un même pas.
            """

            state: PipelineState

        builder = StateGraph(GraphState)

        # 1. Un nœud par agent.
        for agent in self.agents.ordered():
            builder.add_node(agent.name, self._wrap(agent))

        # 2. Arêtes linéaires.
        for source, target in LINEAR_EDGES.items():
            builder.add_edge(source, LG_END if target == END else target)

        # 3. Arêtes conditionnelles (les boucles de feedback).
        builder.add_conditional_edges(
            "quality_gate",
            self._router("quality_gate"),
            {"content_writer": "content_writer", "publisher": "publisher"},
        )
        builder.add_conditional_edges(
            "publisher",
            self._router("publisher"),
            {"content_writer": "content_writer", "analytics_tracker": "analytics_tracker"},
        )

        builder.set_entry_point(ENTRY_POINT)
        return builder.compile()

    @staticmethod
    def _wrap(agent):
        """Adapte un agent à la signature attendue par LangGraph."""

        def node(payload: dict[str, Any]) -> dict[str, Any]:
            state: PipelineState = payload["state"]
            return {"state": agent(state)}

        node.__name__ = agent.name
        return node

    def _router(self, node_name: str):
        route_fn = ROUTES[node_name]

        def router(payload: dict[str, Any]) -> str:
            return route_fn(payload["state"], self.max_revisions)

        return router

    # ------------------------------------------------------------------ #
    def run(self, state: PipelineState) -> PipelineState:
        result = self._compiled.invoke(
            {"state": state},
            config={"recursion_limit": self.recursion_limit},
        )
        final: PipelineState = result["state"]
        if final.run.status is RunStatus.RUNNING:
            final.run.finish(RunStatus.FAILED)
        return final

    def describe(self) -> str:
        """Diagramme Mermaid du graphe, pratique pour la documentation."""
        try:
            return self._compiled.get_graph().draw_mermaid()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Diagramme Mermaid indisponible : %s", exc)
            return ""


# --------------------------------------------------------------------------- #
def build_orchestrator(agents: AgentBundle, *, preferred: str = "langgraph", max_revisions: int = 2):
    """Fabrique l'orchestrateur demandé, avec repli automatique.

    `preferred="langgraph"` mais LangGraph absent → orchestrateur séquentiel,
    avec un simple avertissement dans les logs. Le pipeline ne s'arrête jamais
    pour cette raison.
    """
    if preferred == "sequential":
        logger.info("Orchestrateur : séquentiel (choisi explicitement)")
        return SequentialOrchestrator(agents, max_revisions=max_revisions)

    if not langgraph_available():
        logger.warning(
            "LangGraph n'est pas installé (`pip install langgraph`) : "
            "repli sur l'orchestrateur séquentiel, comportement identique."
        )
        return SequentialOrchestrator(agents, max_revisions=max_revisions)

    try:
        orchestrator = LangGraphOrchestrator(agents, max_revisions=max_revisions)
        logger.info("Orchestrateur : LangGraph (9 nœuds, 2 boucles de feedback)")
        return orchestrator
    except Exception as exc:  # noqa: BLE001
        logger.warning("Compilation du graphe LangGraph impossible (%s) : repli séquentiel", exc)
        return SequentialOrchestrator(agents, max_revisions=max_revisions)
