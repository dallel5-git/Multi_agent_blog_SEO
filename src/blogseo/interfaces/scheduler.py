"""Planificateur local : un article chaque semaine (tous les 7 jours).

## Pourquoi APScheduler et pas GitHub Actions ?

La décision est dictée par le besoin métier : quand vous répondez ❌ sur
Telegram, l'article doit être **écrit dans le dossier du blog sur votre PC**
(`.../oussama-blog/content/articles`) pour que vous le relisiez et le poussiez
vous-même. Un runner GitHub Actions tourne dans un conteneur jetable dans le
cloud : il n'a aucun accès à votre disque. Le pipeline doit donc s'exécuter
là où vivent vos fichiers.

Bénéfices annexes : le modèle d'embeddings (90 Mo) reste en cache local, ChromaDB
persiste entre les runs, et la validation Telegram peut attendre 24 h sans
consommer de minutes CI.

Le workflow GitHub Actions fourni dans `.github/workflows/` reste utilisable
pour les tests d'intégration ; il n'est pas le chemin de publication.

## Lancement

    python -m blogseo.interfaces.scheduler          # au premier plan
    ./scripts/install_systemd_timer.sh              # en service utilisateur
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime, timedelta

from ..application.use_cases.generate_article import GenerateArticleUseCase
from ..infrastructure.config.container import Container
from ..infrastructure.config.logging_config import setup_logging
from ..infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)

#: Intervalle demandé : un article chaque semaine (7 jours = 168 heures).
INTERVAL_HOURS = 168
#: Heure de déclenchement (fuseau local de la machine).
DEFAULT_HOUR = 9
DEFAULT_MINUTE = 0


def run_once(*, dry_run: bool = False) -> None:
    """Exécute un run complet — c'est la fonction planifiée."""
    settings = Settings.from_env()
    settings.storage.ensure()
    container = Container(settings)

    use_case = GenerateArticleUseCase(
        container.orchestrator,
        article_source=container.article_source,
        history=container.history,
        run_repository=container.run_repository,
        notifier=container.telegram,
        analytics=container.analytics,
    )
    state = use_case.execute(dry_run=dry_run)
    logger.info("Run planifié terminé : %s", state.run.summary())


def start(*, dry_run: bool = False, run_immediately: bool = False) -> int:
    """Démarre le planificateur au premier plan (Ctrl+C pour arrêter)."""
    settings = Settings.from_env()
    settings.storage.ensure()
    setup_logging(settings.log_level, settings.storage.logs)

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore[import-not-found]
        from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "APScheduler absent (`pip install apscheduler`) : repli sur une boucle simple."
        )
        return _naive_loop(dry_run=dry_run, run_immediately=run_immediately)

    scheduler = BlockingScheduler(timezone="Africa/Tunis")
    first_run = datetime.now().replace(hour=DEFAULT_HOUR, minute=DEFAULT_MINUTE,
                                       second=0, microsecond=0)
    if run_immediately:
        first_run = datetime.now() + timedelta(seconds=5)
    elif first_run <= datetime.now():
        first_run += timedelta(days=1)

    scheduler.add_job(
        run_once,
        trigger=IntervalTrigger(hours=INTERVAL_HOURS, start_date=first_run),
        kwargs={"dry_run": dry_run},
        id="blogseo_pipeline",
        name="Génération d'article chaque semaine (7 jours)",
        max_instances=1,       # jamais deux pipelines en parallèle
        coalesce=True,         # une seule exécution si des déclenchements ont été manqués
        misfire_grace_time=3600,
    )

    logger.info(
        "Planificateur démarré — prochain run le %s, puis toutes les %s h (%s jours)%s",
        first_run.strftime("%d/%m/%Y à %H:%M"), INTERVAL_HOURS, INTERVAL_HOURS // 24,
        " (mode dry-run)" if dry_run else "",
    )

    def _stop(signum, frame):  # pragma: no cover
        logger.info("Arrêt demandé, extinction du planificateur…")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    scheduler.start()
    return 0


def _naive_loop(*, dry_run: bool, run_immediately: bool) -> int:
    """Repli sans APScheduler : boucle `sleep` toute simple."""
    interval_s = INTERVAL_HOURS * 3600
    if not run_immediately:
        logger.info("Première exécution dans %s h (%s jours)", INTERVAL_HOURS, INTERVAL_HOURS // 24)
        time.sleep(interval_s)
    while True:
        try:
            run_once(dry_run=dry_run)
        except Exception:  # noqa: BLE001 - le planificateur ne doit jamais mourir
            logger.exception("Run planifié en échec — nouvelle tentative au prochain cycle")
        logger.info("Prochain run dans %s h (%s jours)", INTERVAL_HOURS, INTERVAL_HOURS // 24)
        time.sleep(interval_s)


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Planificateur local du pipeline (hebdomadaire / chaque semaine)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", action="store_true", help="Déclenche un premier run immédiatement")
    parsed = parser.parse_args()
    sys.exit(start(dry_run=parsed.dry_run, run_immediately=parsed.now))
