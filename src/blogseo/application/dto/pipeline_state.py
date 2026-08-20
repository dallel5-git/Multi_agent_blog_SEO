"""`PipelineState` : l'objet qui circule entre les 9 agents.

C'est le contrat d'échange du pipeline. Chaque agent lit certains champs et en
écrit d'autres ; aucun agent n'appelle directement un autre agent. C'est ce qui
rend l'ajout ou le retrait d'un agent trivial.

Compatible LangGraph : la classe est convertible en dictionnaire et
reconstructible, ce qui permet de l'utiliser comme état de graphe.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from ...domain.entities.article import Article
from ...domain.entities.pipeline_run import PipelineRun
from ...domain.entities.review import ReviewResult
from ...domain.entities.topic import Topic
from ...domain.entities.trend import TrendDigest
from ...domain.ports.analytics import PerformanceFeedback
from ...domain.ports.repositories import PublishedArticleRef
from ...domain.value_objects.quality_report import QualityReport


@dataclass(slots=True)
class PipelineState:
    """État mutable partagé par tous les agents d'un run."""

    run: PipelineRun

    # --- Entrées / contexte ------------------------------------------- #
    existing_articles: list[PublishedArticleRef] = field(default_factory=list)
    performance_feedback: PerformanceFeedback = field(default_factory=PerformanceFeedback)

    # --- Agent 1 : Trend Scout ---------------------------------------- #
    global_digest: TrendDigest | None = None
    global_themes: list[dict] = field(default_factory=list)

    # --- Agent 2 : Tunisia Watcher ------------------------------------ #
    tunisia_digest: TrendDigest | None = None
    tunisia_context: dict = field(default_factory=dict)
    trends_scores: dict[str, float] = field(default_factory=dict)

    # --- Agent 3 : Keyword Analyst ------------------------------------ #
    topic: Topic | None = None
    rejected_titles: list[str] = field(default_factory=list)
    topic_attempts: int = 0

    # --- Agent 4 : Content Writer ------------------------------------- #
    article: Article | None = None
    revision_instructions: str = ""
    iteration: int = 0

    # --- Agent 5 : Technical Reviewer --------------------------------- #
    review: ReviewResult | None = None

    # --- Agent 7 : Quality Gate --------------------------------------- #
    quality: QualityReport | None = None

    # --- Agent 8 : Publisher ------------------------------------------ #
    draft_path: str = ""
    published_path: str = ""
    cover_path: str = ""
    commit_sha: str = ""

    # --- Divers -------------------------------------------------------- #
    warnings: list[str] = field(default_factory=list)
    research_context: str = ""

    # ------------------------------------------------------------------ #
    @property
    def existing_titles(self) -> list[str]:
        return [a.title for a in self.existing_articles]

    @property
    def existing_slugs(self) -> list[str]:
        return [a.slug for a in self.existing_articles]

    @property
    def existing_tags(self) -> list[str]:
        return [tag for a in self.existing_articles for tag in a.tags]

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    # -- Interop LangGraph --------------------------------------------- #
    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineState:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})
