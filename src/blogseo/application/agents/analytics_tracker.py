"""Agent 9/9 — Analytics Tracker (stub v1).

Rôle prévu : ingérer les performances des articles publiés (Search Console,
Plausible, Umami…) et renvoyer un signal au Keyword Analyst pour orienter les
prochains sujets — c'est la seconde boucle de rétroaction du système.

Dans la v1, l'agent :
- réindexe le nouvel article dans le vector store (indispensable pour que
  l'anti-doublon du prochain run le connaisse) ;
- charge un éventuel export manuel de performances et construit le feedback ;
- écrit une trace de fin de run.

Aucune clé d'API n'est requise. Brancher la vraie Search Console consistera à
fournir un autre adapter du port `AnalyticsPort`, sans toucher à cet agent.
"""

from __future__ import annotations

from ...domain.entities.pipeline_run import RunStatus
from ...domain.ports.analytics import AnalyticsPort
from ...domain.ports.repositories import ArticleHistoryPort, PublishedArticleRef
from ..dto.pipeline_state import PipelineState
from .base import Agent


class AnalyticsTrackerAgent(Agent):
    """Boucle de rétroaction performance + réindexation anti-doublon."""

    name = "analytics_tracker"
    label = "Analytics Tracker — indexation et feedback"
    critical = False

    def __init__(
        self,
        analytics: AnalyticsPort,
        history: ArticleHistoryPort,
        *,
        index_new_article: bool = True,
    ) -> None:
        super().__init__()
        self.analytics = analytics
        self.history = history
        self.index_new_article = index_new_article

    def run(self, state: PipelineState) -> PipelineState:
        # 1. Réindexation : le prochain run ne doit pas re-proposer ce sujet.
        #    On indexe dès que l'article a été écrit dans le blog, que le push
        #    ait eu lieu ou non — l'auteur le poussera peut-être manuellement.
        should_index = (
            self.index_new_article
            and state.article is not None
            and not state.run.dry_run
            and state.run.status in (RunStatus.PUBLISHED, RunStatus.SAVED_LOCALLY)
            and bool(state.published_path)
        )
        if should_index:
            article = state.article
            self.history.index([
                PublishedArticleRef(
                    slug=article.slug.value,
                    title=article.seo.meta_title or article.title,
                    description=article.seo.meta_description,
                    category=article.category.value,
                    date=article.published_on.isoformat(),
                    tags=article.tags,
                )
            ])
            self.logger.info("Article « %s » ajouté à l'index anti-doublon", article.slug)
        else:
            self.logger.info("Pas d'indexation (dry-run ou article non écrit dans le blog)")

        # 2. Ingestion des performances (stub : export manuel optionnel).
        performances = self.analytics.fetch_performance(days=28)
        feedback = self.analytics.build_feedback(performances)
        state.performance_feedback = feedback

        if feedback.is_empty:
            self.logger.info(
                "Aucun signal de performance. Pour l'activer, déposez un export Search Console "
                "au format JSON dans storage/analytics/performance.json"
            )
        else:
            self.logger.info("Feedback de performance prêt pour le prochain run :\n%s",
                             feedback.as_context_block())

        # 3. Statut final si personne ne l'a encore fixé.
        if state.run.status is RunStatus.RUNNING:
            state.run.finish(RunStatus.SAVED_LOCALLY if state.draft_path else RunStatus.FAILED)
        return state

    def describe(self, state: PipelineState) -> str:
        indexed = self.history.count()
        return f"{indexed} article(s) indexé(s), feedback {'vide' if state.performance_feedback.is_empty else 'disponible'}"
