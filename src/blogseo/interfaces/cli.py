"""Interface en ligne de commande.

Commandes disponibles :

    blogseo run            Lance le pipeline complet
    blogseo run --dry-run  Idem, sans écrire dans le blog ni pousser sur Git
    blogseo check          Vérifie la configuration et les dépendances
    blogseo index          (Ré)indexe les articles existants pour l'anti-doublon
    blogseo runs           Liste les derniers runs
    blogseo show <run_id>  Détaille un run
    blogseo dashboard      Génère un tableau de bord HTML local des runs
    blogseo graph          Affiche le diagramme Mermaid du pipeline
    blogseo series start   Planifie une série de 3 à 5 articles liés
    blogseo series list    Liste les séries planifiées
    blogseo series show    Détaille une série
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from ..application.dto.pipeline_state import PipelineState
from ..application.use_cases.generate_article import GenerateArticleUseCase
from ..domain.entities.pipeline_run import PipelineRun, RunStatus
from ..infrastructure.config.container import Container
from ..infrastructure.config.logging_config import setup_logging
from ..infrastructure.config.settings import Settings
from .dashboard import write_dashboard

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blogseo",
        description="Système multi-agents de génération d'articles de blog SEO (100 %% gratuit).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  blogseo check                      # vérifier la configuration\n"
            "  blogseo run --dry-run --offline    # tester sans clé API ni réseau\n"
            "  blogseo run --dry-run              # tester avec les vrais LLM, sans publier\n"
            "  blogseo run                        # run complet avec validation Telegram\n"
        ),
    )
    parser.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Lance le pipeline complet")
    run_cmd.add_argument("--dry-run", action="store_true",
                         help="N'écrit rien dans le blog et ne pousse rien sur Git")
    run_cmd.add_argument("--offline", action="store_true",
                         help="Aucun appel réseau : LLM factice, ni recherche ni Telegram")
    run_cmd.add_argument("--no-human-review", action="store_true",
                         help="Publie sans attendre la validation Telegram (déconseillé)")
    run_cmd.add_argument("--orchestrator", choices=["langgraph", "sequential"], default=None)
    run_cmd.add_argument("--print", dest="print_article", action="store_true",
                         help="Affiche l'article final dans le terminal")

    sub.add_parser("check", help="Vérifie la configuration et les dépendances")
    sub.add_parser("index", help="(Ré)indexe les articles existants pour l'anti-doublon")
    sub.add_parser("graph", help="Affiche le diagramme Mermaid du pipeline")

    runs_cmd = sub.add_parser("runs", help="Liste les derniers runs")
    runs_cmd.add_argument("-n", "--limit", type=int, default=10)

    show_cmd = sub.add_parser("show", help="Détaille un run")
    show_cmd.add_argument("run_id")

    dashboard_cmd = sub.add_parser("dashboard", help="Génère un tableau de bord HTML local des runs")
    dashboard_cmd.add_argument("-o", "--output", type=Path, default=None,
                               help="Chemin du fichier HTML (défaut : storage/dashboard.html)")
    dashboard_cmd.add_argument("--open", dest="open_browser", action="store_true",
                               help="Ouvre la page dans le navigateur après génération")

    series_cmd = sub.add_parser("series", help="Planifie et suit une série d'articles liés")
    series_sub = series_cmd.add_subparsers(dest="series_action", required=True)

    series_start = series_sub.add_parser("start", help="Planifie une nouvelle série (3 à 5 articles)")
    series_start.add_argument("theme", help="Thème commun de la série")
    series_start.add_argument("--size", type=int, default=4,
                              help="Nombre d'articles de la série (3 à 5, défaut : 4)")
    series_start.add_argument("--offline", action="store_true",
                              help="Aucun appel réseau : LLM factice")

    series_sub.add_parser("list", help="Liste les séries planifiées")

    series_show = series_sub.add_parser("show", help="Détaille une série")
    series_show.add_argument("series_id")

    return parser


# --------------------------------------------------------------------------- #
def cmd_check(container: Container) -> int:
    settings = container.settings
    print("\n╭─ Configuration ─────────────────────────────────────────────────────────╮")
    print(settings.describe())
    print("╰─────────────────────────────────────────────────────────────────────────╯\n")

    problems: list[str] = []
    notes: list[str] = []

    if not settings.llm.has_any_provider:
        notes.append("Aucune clé LLM : le pipeline tournera avec le LLM factice (articles d'exemple).")
    if not settings.telegram.is_configured and settings.human_review:
        notes.append("Telegram non configuré : sans validation, les articles resteront en local.")
    if not settings.search_console.is_configured:
        notes.append(
            "Search Console non configuré : le Keyword Analyst travaillera sans retour de "
            "performance (voir scripts/search_console_oauth.py)."
        )

    content_dir = settings.publishing.blog_content_dir
    if not content_dir.exists():
        problems.append(f"Dossier d'articles introuvable : {content_dir}")
    repo_dir = settings.publishing.blog_repo_dir
    if not (repo_dir / ".git").exists():
        notes.append(f"{repo_dir} n'est pas un dépôt Git : le bouton ✅ ne pourra pas pousser.")

    print("Dépendances optionnelles :")
    for module, purpose in [
        ("langgraph", "orchestration en graphe"),
        ("chromadb", "vector store anti-doublon persistant"),
        ("sentence_transformers", "embeddings sémantiques locaux"),
        ("ddgs", "recherche DuckDuckGo"),
        ("pytrends", "Google Trends"),
        ("PIL", "image de couverture de secours"),
        ("apscheduler", "planification locale toutes les 48 h"),
    ]:
        try:
            __import__(module)
            status = "✅"
        except ImportError:
            status = "⚠️ "
            notes.append(f"{module} absent → {purpose} dégradé(e)")
        print(f"  {status} {module:<24} {purpose}")

    print(f"\nArticles détectés dans le blog : {len(container.article_source.list_published())}")
    print(f"Entrées dans l'index anti-doublon : {container.history.count()}")

    if notes:
        print("\nRemarques :")
        for note in notes:
            print(f"  • {note}")
    if problems:
        print("\nProblèmes bloquants :")
        for problem in problems:
            print(f"  ✖ {problem}")
        return EXIT_CONFIG

    print("\n✅ Configuration exploitable.\n")
    return EXIT_OK


def cmd_index(container: Container) -> int:
    articles = container.article_source.list_published()
    if not articles:
        print("Aucun article trouvé dans", container.settings.publishing.blog_content_dir)
        return EXIT_ERROR
    count = container.history.index(articles)
    print(f"✅ {count} article(s) indexé(s). Total dans l'index : {container.history.count()}")
    return EXIT_OK


def cmd_graph(container: Container) -> int:
    orchestrator = container.orchestrator
    diagram = getattr(orchestrator, "describe", lambda: "")()
    if diagram:
        print(diagram)
    else:
        print("Orchestrateur séquentiel — pipeline :")
        for index, agent in enumerate(container.agents.ordered(), start=1):
            print(f"  {index}. {agent.name:<20} {agent.label}")
        print("\n  Boucles : quality_gate → content_writer, publisher(🔁) → content_writer")
    return EXIT_OK


def cmd_runs(container: Container, limit: int) -> int:
    runs = container.run_repository.list_recent(limit)
    if not runs:
        print("Aucun run enregistré.")
        return EXIT_OK
    print(f"\n{'RUN':<14}{'STATUT':<18}{'DURÉE':>8}  {'QUALITÉ':>8}  SUJET")
    print("─" * 100)
    for run in runs:
        print(
            f"{run.run_id:<14}{run.status.value:<18}{run.duration_s:>7.0f}s"
            f"{run.quality_score:>9.0%}  {run.topic_title[:44]}"
        )
    print()
    return EXIT_OK


def cmd_show(container: Container, run_id: str) -> int:
    run = container.run_repository.get(run_id)
    if run is None:
        print(f"Run {run_id} introuvable.")
        return EXIT_ERROR

    print(f"\nRun {run.run_id} — {run.status.value}")
    print(f"  Sujet     : {run.topic_title}")
    print(f"  Slug      : {run.article_slug}")
    print(f"  Décision  : {run.decision.value if run.decision else '—'}")
    print(f"  Qualité   : {run.quality_score:.0%} (révisions : {run.revision_count})")
    print(f"  Brouillon : {run.draft_path or '—'}")
    print(f"  Publié    : {run.published_path or '—'}")
    print(f"  Commit    : {run.commit_sha or '—'}")
    print(f"  Durée     : {run.duration_s}s\n")
    print("  Étapes :")
    for step in run.steps:
        mark = "✔" if step.ok else "✖"
        print(f"    {mark} {step.name:<22}{step.duration_s:>7.1f}s  {step.detail}")
    if run.errors:
        print("\n  Erreurs :")
        for error in run.errors:
            print(f"    ✖ {error}")
    print()
    return EXIT_OK


def cmd_dashboard(container: Container, output: Path | None, open_browser: bool) -> int:
    runs = container.run_repository.list_recent(limit=100_000)
    output_path = output or (container.settings.storage.root / "dashboard.html")

    if not runs:
        print("Aucun run enregistré : le tableau de bord sera vide. Lancez `blogseo run` d'abord.")

    written = write_dashboard(runs, output_path)
    print(f"✅ Tableau de bord généré : {written} ({len(runs)} run(s))")
    print(f"   Ouvrez-le directement dans un navigateur : file://{written.resolve()}")

    if open_browser:
        webbrowser.open(f"file://{written.resolve()}")

    return EXIT_OK


_SERIES_STATUS_MARK = {"pending": "⏳", "written": "📝", "published": "✅", "skipped": "⏭ "}


def cmd_series_start(container: Container, theme: str, size: int) -> int:
    if not 3 <= size <= 5:
        print("La taille d'une série doit être comprise entre 3 et 5 articles.")
        return EXIT_ERROR

    state = PipelineState(run=PipelineRun())
    state.existing_articles = container.article_source.list_published()
    series = container.agents.keyword_analyst.plan_series(state, theme=theme, size=size)

    print(f"\n✅ {series.summary()}")
    print(f"   ID : {series.series_id}\n")
    for index, topic in enumerate(series.topics, start=1):
        print(f"  {index}. {topic.title}  [{topic.category.value}]")
    print(
        "\nLe prochain `blogseo run` consommera automatiquement le premier sujet de "
        "cette série.\n"
    )
    return EXIT_OK


def cmd_series_list(container: Container) -> int:
    all_series = container.series_repository.list_all()
    if not all_series:
        print("Aucune série planifiée. Utilisez `blogseo series start \"<thème>\"`.")
        return EXIT_OK

    print(f"\n{'ID':<20}{'STATUT':<12}SÉRIE")
    print("─" * 90)
    for series in all_series:
        status = "active" if series.is_active else "terminée"
        print(f"{series.series_id:<20}{status:<12}{series.summary()}")
    print()
    return EXIT_OK


def cmd_series_show(container: Container, series_id: str) -> int:
    series = container.series_repository.get(series_id)
    if series is None:
        print(f"Série {series_id} introuvable.")
        return EXIT_ERROR

    print(f"\nSérie {series.series_id} — {series.title}")
    print(f"  Thème : {series.theme}\n")
    for index, topic in enumerate(series.topics, start=1):
        mark = _SERIES_STATUS_MARK.get(topic.status, "?")
        slug_suffix = f"  → {topic.slug}" if topic.slug else ""
        print(f"  {mark} {index}. {topic.title}  [{topic.status}]{slug_suffix}")
    print()
    return EXIT_OK


def cmd_run(container: Container, args) -> int:
    use_case = GenerateArticleUseCase(
        container.orchestrator,
        article_source=container.article_source,
        history=container.history,
        run_repository=container.run_repository,
        notifier=container.telegram,
        analytics=container.analytics,
    )
    state = use_case.execute(dry_run=args.dry_run)

    print("\n" + "═" * 78)
    print(f"RÉSULTAT — run {state.run.run_id} : {state.run.status.value}")
    print("═" * 78)
    if state.article:
        article = state.article
        print(f"  Titre       : {article.seo.meta_title}")
        print(f"  Description : {article.seo.meta_description}")
        print(f"  Slug        : {article.slug}")
        print(f"  Catégorie   : {article.category.value}")
        print(f"  Tags        : {', '.join(article.tags)}")
        print(f"  Longueur    : {article.word_count} mots, {article.h2_count} sections")
        if state.quality:
            print(f"  Qualité     : {state.quality.summary()}")
        print(f"  Brouillon   : {state.draft_path}")
        if state.published_path:
            print(f"  Publié      : {state.published_path}")
        if state.commit_sha:
            print(f"  Commit      : {state.commit_sha}")
    else:
        print("  Aucun article produit.")
    if state.warnings:
        print("\n  Avertissements :")
        for warning in state.warnings:
            print(f"    ⚠ {warning}")
    print("═" * 78 + "\n")

    if args.print_article and state.article:
        print(state.article.to_mdx())

    return EXIT_OK if state.run.status is not RunStatus.FAILED else EXIT_ERROR


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()

    # Les options de la CLI l'emportent sur `.env`.
    overrides: dict = {}
    if args.log_level:
        overrides["log_level"] = args.log_level
    if getattr(args, "no_human_review", False):
        overrides["human_review"] = False
    if getattr(args, "orchestrator", None):
        overrides["orchestrator"] = args.orchestrator
    if getattr(args, "dry_run", False):
        overrides["dry_run"] = True
    if overrides:
        from dataclasses import replace

        settings = replace(settings, **overrides)

    settings.storage.ensure()
    setup_logging(settings.log_level, settings.storage.logs)

    container = Container(settings, offline=getattr(args, "offline", False))

    if args.command == "check":
        return cmd_check(container)
    if args.command == "index":
        return cmd_index(container)
    if args.command == "graph":
        return cmd_graph(container)
    if args.command == "runs":
        return cmd_runs(container, args.limit)
    if args.command == "show":
        return cmd_show(container, args.run_id)
    if args.command == "dashboard":
        return cmd_dashboard(container, args.output, args.open_browser)
    if args.command == "series":
        if args.series_action == "start":
            return cmd_series_start(container, args.theme, args.size)
        if args.series_action == "list":
            return cmd_series_list(container)
        if args.series_action == "show":
            return cmd_series_show(container, args.series_id)
    if args.command == "run":
        return cmd_run(container, args)

    return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
