"""Cas d'usage principal : « générer (et éventuellement publier) un article ».

C'est le point d'entrée applicatif appelé par la CLI et par le scheduler. Il
orchestre les préliminaires (chargement de l'historique, indexation), délègue au
graphe, puis persiste et notifie le résultat.
"""

from __future__ import annotations

import logging

from ...domain.entities.pipeline_run import PipelineRun, RunStatus
from ...domain.errors import BlogSeoError
from ...domain.ports.notifications import NotifierPort
from ...domain.ports.repositories import ArticleHistoryPort, ArticleSourcePort, RunRepositoryPort
from ..dto.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


class GenerateArticleUseCase:
    """Exécute un run complet du pipeline."""

    def __init__(
        self,
        orchestrator,
        *,
        article_source: ArticleSourcePort,
        history: ArticleHistoryPort,
        run_repository: RunRepositoryPort,
        notifier: NotifierPort | None = None,
        analytics=None,
    ) -> None:
        self.orchestrator = orchestrator
        self.article_source = article_source
        self.history = history
        self.run_repository = run_repository
        self.notifier = notifier
        self.analytics = analytics

    # ------------------------------------------------------------------ #
    def execute(self, *, dry_run: bool = False) -> PipelineState:
        run = PipelineRun(dry_run=dry_run)
        state = PipelineState(run=run)
        logger.info("═" * 78)
        logger.info("Démarrage du run %s%s", run.run_id, " (DRY-RUN)" if dry_run else "")
        logger.info("═" * 78)

        try:
            self._prepare(state)
            state = self.orchestrator.run(state)
        except BlogSeoError as exc:
            logger.error("Run %s interrompu : %s", run.run_id, exc)
            run.errors.append(str(exc))
            run.finish(RunStatus.FAILED)
            self._notify_failure(state, exc)
        except Exception as exc:  # noqa: BLE001 - on veut toujours persister le run
            logger.exception("Run %s : erreur inattendue", run.run_id)
            run.errors.append(f"{type(exc).__name__}: {exc}")
            run.finish(RunStatus.FAILED)
            self._notify_failure(state, exc)
        finally:
            self.run_repository.save(state.run)
            logger.info("═" * 78)
            logger.info("Fin du run — %s", state.run.summary())
            for warning in state.warnings:
                logger.warning("  ⚠ %s", warning)
            logger.info("═" * 78)

        return state

    # ------------------------------------------------------------------ #
    def _prepare(self, state: PipelineState) -> None:
        """Charge l'historique du blog et (ré)indexe le vector store anti-doublon."""
        trace = state.run.start_step("bootstrap")

        articles = self.article_source.list_published()
        state.existing_articles = articles

        if articles:
            # On réindexe systématiquement : l'auteur peut avoir ajouté un article
            # à la main entre deux runs, et l'anti-doublon doit en tenir compte.
            self.history.index(articles)
        logger.info(
            "Historique : %s article(s) publié(s), %s entrée(s) dans l'index sémantique",
            len(articles), self.history.count(),
        )

        # Feedback de performance (stub v1 : export manuel optionnel).
        if self.analytics is not None:
            performances = self.analytics.fetch_performance(days=28)
            state.performance_feedback = self.analytics.build_feedback(performances)

        state.run.end_step(trace, ok=True, detail=f"{len(articles)} articles connus")

    def _notify_failure(self, state: PipelineState, exc: BaseException) -> None:
        if self.notifier is None:
            return
        self.notifier.send(
            f"❌ <b>Pipeline en échec</b> — run <code>{state.run.run_id}</code>\n"
            f"<b>{type(exc).__name__}</b>\n"
            f"{str(exc)[:600]}\n\n"
            f"Étapes exécutées : {len(state.run.steps)}"
        )
