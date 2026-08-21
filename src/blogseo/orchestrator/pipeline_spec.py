"""Description déclarative du pipeline : nœuds, ordre et boucles de feedback.

Un seul endroit décrit la topologie. Les deux exécuteurs (LangGraph et
séquentiel) la consomment, ce qui garantit qu'ils se comportent identiquement.

**Ajouter un agent** = l'insérer dans `AgentBundle.ordered()` et, si besoin,
déclarer une condition dans `ROUTES`. Rien d'autre à modifier.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..application.agents.analytics_tracker import AnalyticsTrackerAgent
from ..application.agents.base import Agent
from ..application.agents.content_writer import ContentWriterAgent
from ..application.agents.keyword_analyst import KeywordAnalystAgent
from ..application.agents.publisher import PublisherAgent
from ..application.agents.quality_gate import QualityGateAgent
from ..application.agents.seo_editor import SeoEditorAgent
from ..application.agents.social_writer import SocialWriterAgent
from ..application.agents.technical_reviewer import TechnicalReviewerAgent
from ..application.agents.trend_scout import TrendScoutAgent
from ..application.agents.tunisia_watcher import TunisiaWatcherAgent
from ..application.dto.pipeline_state import PipelineState
from ..domain.entities.pipeline_run import Decision

#: Nom du nœud terminal.
END = "__end__"


@dataclass(slots=True)
class AgentBundle:
    """Les 10 agents du pipeline, dans l'ordre d'exécution."""

    trend_scout: TrendScoutAgent
    tunisia_watcher: TunisiaWatcherAgent
    keyword_analyst: KeywordAnalystAgent
    content_writer: ContentWriterAgent
    technical_reviewer: TechnicalReviewerAgent
    seo_editor: SeoEditorAgent
    quality_gate: QualityGateAgent
    publisher: PublisherAgent
    social_writer: SocialWriterAgent
    analytics_tracker: AnalyticsTrackerAgent

    def ordered(self) -> list[Agent]:
        """Ordre nominal du pipeline (sans les boucles)."""
        return [
            self.trend_scout,
            self.tunisia_watcher,
            self.keyword_analyst,
            self.content_writer,
            self.technical_reviewer,
            self.seo_editor,
            self.quality_gate,
            self.publisher,
            self.social_writer,
            self.analytics_tracker,
        ]

    def by_name(self) -> dict[str, Agent]:
        return {agent.name: agent for agent in self.ordered()}


# --------------------------------------------------------------------------- #
# Routage conditionnel
# --------------------------------------------------------------------------- #
def route_after_quality_gate(state: PipelineState, max_revisions: int) -> str:
    """Boucle de feedback n°1 : Quality Gate → Content Writer.

    - Article approuvé → on passe au Publisher.
    - Article rejeté et itérations restantes → retour au Content Writer.
    - Article rejeté sans itération restante → on passe quand même au Publisher :
      l'article part en validation humaine avec ses avertissements affichés.
      Mieux vaut une décision humaine informée qu'un run perdu.
    """
    report = state.quality
    if report is None or report.approved:
        return "publisher"

    if state.iteration <= max_revisions:
        return "content_writer"

    state.warn(
        f"Quality Gate toujours en échec après {state.iteration} rédaction(s) : "
        f"{len(report.blockers)} point(s) bloquant(s) transmis à la validation humaine."
    )
    # On repasse les blocages restants dans les avertissements du message Telegram.
    return "publisher"


def route_after_publisher(state: PipelineState, max_revisions: int) -> str:
    """Boucle de feedback n°2 : Publisher (bouton 🔁) → Content Writer."""
    if state.run.decision is Decision.REWRITE and state.iteration <= max_revisions + 2:
        return "content_writer"
    return "social_writer"


#: Arêtes conditionnelles du graphe : nœud source → fonction de routage.
ROUTES = {
    "quality_gate": route_after_quality_gate,
    "publisher": route_after_publisher,
}

#: Arêtes linéaires : nœud source → nœud cible.
LINEAR_EDGES = {
    "trend_scout": "tunisia_watcher",
    "tunisia_watcher": "keyword_analyst",
    "keyword_analyst": "content_writer",
    "content_writer": "technical_reviewer",
    "technical_reviewer": "seo_editor",
    "seo_editor": "quality_gate",
    "social_writer": "analytics_tracker",
    "analytics_tracker": END,
}

ENTRY_POINT = "trend_scout"
