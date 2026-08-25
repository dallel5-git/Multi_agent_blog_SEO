"""Interface en ligne de commande du pilotage multi-plateformes.

Commandes disponibles :

    pilotage migrate            Applique le schéma SQL du calendrier partagé
    pilotage check               Vérifie la configuration du pilotage
    pilotage sync-blog           Verse les articles publiés du blog dans le calendrier
    pilotage run <plateforme>    Lance un pipeline (watch → choose_topic → write → submit)
"""

from __future__ import annotations

import argparse
import sys

from .brand_kernel.loader import load_brand_kernel
from .config.settings import PilotageSettings
from .pipelines.base import PlatformPipeline
from .pipelines.facebook import FacebookPipeline
from .pipelines.instagram import InstagramPipeline
from .pipelines.telegram_channel import TelegramChannelPipeline
from .pipelines.tiktok import TikTokPipeline
from .pipelines.x import XPipeline
from .pipelines.youtube import YouTubePipeline
from .platforms import Platform
from .shared_calendar.blog_bridge import sync_blog_articles
from .shared_calendar.migrate import apply_schema
from .shared_calendar.repository import CalendarRepository

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2

#: Un pipeline implémenté par plateforme. Étendre cette table est le SEUL
#: endroit à toucher pour brancher un nouveau pipeline sur la CLI — le
#: pipeline lui-même n'a besoin de rien connaître d'ici.
_PIPELINES: dict[Platform, type[PlatformPipeline]] = {
    Platform.YOUTUBE: YouTubePipeline,
    Platform.TIKTOK: TikTokPipeline,
    Platform.INSTAGRAM: InstagramPipeline,
    Platform.X: XPipeline,
    Platform.FACEBOOK: FacebookPipeline,
    Platform.TELEGRAM_CHANNEL: TelegramChannelPipeline,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pilotage",
        description="Pilotage de contenu multi-plateformes (100 % gratuit).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Applique le schéma SQL du calendrier partagé")
    sub.add_parser("check", help="Vérifie la configuration du pilotage")
    sub.add_parser("sync-blog", help="Verse les articles publiés du blog dans le calendrier")

    run_cmd = sub.add_parser("run", help="Lance un pipeline de plateforme")
    run_cmd.add_argument("platform", choices=[p.value for p in _PIPELINES])
    run_cmd.add_argument("--offline", action="store_true",
                          help="Aucun appel réseau : veille vide, LLM factice")

    return parser


def cmd_migrate(settings: PilotageSettings) -> int:
    apply_schema(settings.calendar.db_path)
    print(f"✅ Schéma appliqué : {settings.calendar.db_path}")
    return EXIT_OK


def cmd_check(settings: PilotageSettings) -> int:
    print("\n╭─ Configuration pilotage ───────────────────────────────────────────────╮")
    print(settings.describe())
    print("╰─────────────────────────────────────────────────────────────────────────╯\n")

    notes: list[str] = []
    if not settings.bots.configured_platforms:
        notes.append("Aucun bot de pilotage configuré : les brouillons ne seront envoyés nulle part.")
    if not settings.calendar.blog_content_dir.exists():
        notes.append(f"Dossier blog introuvable : {settings.calendar.blog_content_dir}")
    if not settings.calendar.db_path.exists():
        notes.append(f"{settings.calendar.db_path} n'existe pas encore — lancez `pilotage migrate`.")

    if notes:
        print("Remarques :")
        for note in notes:
            print(f"  • {note}")
        print()

    print("✅ Configuration lue.\n")
    return EXIT_OK


def cmd_sync_blog(settings: PilotageSettings) -> int:
    kernel = load_brand_kernel()
    blog_url = kernel.identity.handles.blog
    if not blog_url:
        print("✖ identity.handles.blog n'est pas renseigné dans le Brand Kernel.")
        return EXIT_CONFIG

    repository = CalendarRepository(settings.calendar.db_path)
    try:
        count = sync_blog_articles(repository, settings.calendar.blog_content_dir, blog_url)
    finally:
        repository.close()

    print(f"✅ {count} nouvel(le) article(s) blog synchronisé(s) dans le calendrier.")
    return EXIT_OK


def cmd_run(settings: PilotageSettings, platform_name: str, *, offline: bool) -> int:
    platform = Platform(platform_name)
    pipeline_cls = _PIPELINES[platform]

    repository = CalendarRepository(settings.calendar.db_path)
    try:
        pipeline = pipeline_cls(repository=repository, offline=offline)
        item_id = pipeline.run()
    finally:
        repository.close()

    print(f"✅ Brouillon #{item_id} enregistré pour {platform.label}.")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = PilotageSettings.from_env()

    if args.command == "migrate":
        return cmd_migrate(settings)
    if args.command == "check":
        return cmd_check(settings)
    if args.command == "sync-blog":
        return cmd_sync_blog(settings)
    if args.command == "run":
        return cmd_run(settings, args.platform, offline=args.offline)

    return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
