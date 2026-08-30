"""Interface en ligne de commande du pilotage multi-plateformes.

Commandes disponibles :

    pilotage migrate                Applique le schéma SQL du calendrier partagé
    pilotage check                  Vérifie la configuration du pilotage
    pilotage sync-blog              Verse les articles publiés du blog dans le calendrier
    pilotage run <plateforme>       Lance un pipeline (watch → choose_topic → write → submit)
    pilotage bot <plateforme>       Démarre le bot de pilotage (boucle infinie)
    pilotage remind-stats <plateforme>
                                     Envoie le rappel de saisie manuelle (TikTok, X)
    pilotage collect-stats <plateforme>
                                     Collecte les statistiques automatiques (YouTube, Meta, Telegram)
    pilotage check-meta-token       Vérifie l'échéance du jeton Meta
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date

from .bots.base import PilotageBot
from .bots.facebook import create_bot as create_facebook_bot
from .bots.instagram import create_bot as create_instagram_bot
from .bots.telegram_channel import create_bot as create_telegram_channel_bot
from .bots.tiktok import create_bot as create_tiktok_bot
from .bots.x import create_bot as create_x_bot
from .bots.youtube import create_bot as create_youtube_bot
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
from .stats_collector.base import StatsCollector
from .stats_collector.meta_graph import (
    FacebookStatsCollector,
    InstagramStatsCollector,
    token_renewal_reminder,
)
from .stats_collector.telegram_api import TelegramChannelStatsCollector
from .stats_collector.youtube_api import YouTubeStatsCollector

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

#: Même principe que `_PIPELINES` pour les bots : un seul endroit à étendre.
_BOT_FACTORIES = {
    Platform.YOUTUBE: create_youtube_bot,
    Platform.TIKTOK: create_tiktok_bot,
    Platform.INSTAGRAM: create_instagram_bot,
    Platform.X: create_x_bot,
    Platform.FACEBOOK: create_facebook_bot,
    Platform.TELEGRAM_CHANNEL: create_telegram_channel_bot,
}

#: X et TikTok n'ont volontairement aucune entrée : aucune API gratuite,
#: la collecte passe par les commandes `/mesure` et `/passe` des bots (lot 5).
_COLLECTOR_FACTORIES: dict[Platform, Callable[[PilotageSettings, CalendarRepository], StatsCollector]] = {
    Platform.YOUTUBE: lambda settings, repository: YouTubeStatsCollector(
        repository, api_key=settings.youtube.api_key
    ),
    Platform.FACEBOOK: lambda settings, repository: FacebookStatsCollector(
        repository, page_access_token=settings.meta.page_access_token, page_id=settings.meta.page_id
    ),
    Platform.INSTAGRAM: lambda settings, repository: InstagramStatsCollector(
        repository,
        page_access_token=settings.meta.page_access_token,
        ig_business_id=settings.meta.instagram_business_id,
    ),
    Platform.TELEGRAM_CHANNEL: lambda settings, repository: TelegramChannelStatsCollector(
        repository,
        bot_token=settings.bots.for_platform(Platform.TELEGRAM_CHANNEL).bot_token,
        channel_username=settings.telegram_channel.channel_username,
    ),
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

    bot_cmd = sub.add_parser("bot", help="Démarre le bot de pilotage d'une plateforme")
    bot_cmd.add_argument("platform", choices=[p.value for p in _BOT_FACTORIES])
    bot_cmd.add_argument("--once", action="store_true",
                          help="Un seul tour de sondage (`getUpdates`), utile pour tester")

    remind_cmd = sub.add_parser(
        "remind-stats", help="Envoie le rappel de saisie manuelle des statistiques"
    )
    remind_cmd.add_argument("platform", choices=[p.value for p in _BOT_FACTORIES])

    collect_cmd = sub.add_parser(
        "collect-stats", help="Collecte les statistiques automatiques d'une plateforme"
    )
    collect_cmd.add_argument("platform", choices=[p.value for p in _COLLECTOR_FACTORIES])

    sub.add_parser("check-meta-token", help="Vérifie l'échéance du jeton Meta")

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

        # Transition drafted → pending_review (ARCHITECTURE.md §4) : au
        # mieux, jamais bloquant — un pipeline doit tourner même sans bot
        # configuré (issue #57, critère « aucune source morte... »).
        bot_factory = _BOT_FACTORIES.get(platform)
        if bot_factory is not None:
            bot = bot_factory(settings, repository)
            if bot.is_configured():
                bot.notify_pending_drafts()
    finally:
        repository.close()

    print(f"✅ Brouillon #{item_id} enregistré pour {platform.label}.")
    return EXIT_OK


def _make_bot(settings: PilotageSettings, platform_name: str, repository: CalendarRepository) -> PilotageBot:
    platform = Platform(platform_name)
    bot = _BOT_FACTORIES[platform](settings, repository)
    pipeline_cls = _PIPELINES.get(platform)
    if pipeline_cls is not None:
        def _generate() -> int:
            return pipeline_cls(repository=repository, offline=False).run()

        bot.generate_callback = _generate
    return bot


def cmd_bot(settings: PilotageSettings, platform_name: str, *, once: bool) -> int:
    repository = CalendarRepository(settings.calendar.db_path)
    try:
        bot = _make_bot(settings, platform_name, repository)
        if not bot.is_configured():
            print(f"✖ Bot {platform_name} non configuré (token/chat_id manquant dans .env).")
            return EXIT_CONFIG
        if once:
            traitees = bot.poll_once()
            print(f"✅ 1 tour de sondage effectué ({traitees} mise(s) à jour traitée(s)).")
            return EXIT_OK
        bot.run_forever()  # ne revient jamais tant que le processus tourne
        return EXIT_OK
    finally:
        repository.close()


def cmd_remind_stats(settings: PilotageSettings, platform_name: str) -> int:
    repository = CalendarRepository(settings.calendar.db_path)
    try:
        bot = _make_bot(settings, platform_name, repository)
        if not bot.is_configured():
            print(f"✖ Bot {platform_name} non configuré (token/chat_id manquant dans .env).")
            return EXIT_CONFIG
        message = bot.compose_manual_stats_reminder()
        if message is None:
            print("✅ Rien à rappeler : toutes les publications ont une mesure récente.")
            return EXIT_OK
        bot.send_message(message)
        print("✅ Rappel envoyé.")
        return EXIT_OK
    finally:
        repository.close()


def cmd_collect_stats(settings: PilotageSettings, platform_name: str) -> int:
    platform = Platform(platform_name)
    factory = _COLLECTOR_FACTORIES[platform]

    repository = CalendarRepository(settings.calendar.db_path)
    try:
        collector = factory(settings, repository)
        count = collector.run(date.today())
    finally:
        repository.close()

    print(f"✅ {count} mesure(s) enregistrée(s) pour {platform.label}.")
    return EXIT_OK


def cmd_check_meta_token(settings: PilotageSettings) -> int:
    if not settings.meta.page_access_token:
        print("✖ META_PAGE_ACCESS_TOKEN absent — rien à vérifier.")
        return EXIT_CONFIG

    message = token_renewal_reminder(settings.meta.page_access_token)
    if message is None:
        print("✅ Jeton Meta valide, pas de renouvellement urgent.")
        return EXIT_OK
    print(message)
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
    if args.command == "bot":
        return cmd_bot(settings, args.platform, once=args.once)
    if args.command == "remind-stats":
        return cmd_remind_stats(settings, args.platform)
    if args.command == "collect-stats":
        return cmd_collect_stats(settings, args.platform)
    if args.command == "check-meta-token":
        return cmd_check_meta_token(settings)

    return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
