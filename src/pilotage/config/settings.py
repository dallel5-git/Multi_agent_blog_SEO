"""Configuration `pilotage`, sur le modèle de `blogseo.infrastructure.config.settings`.

RÈGLE ABSOLUE, identique au reste du projet : aucune clé en dur, jamais.
`describe()` affiche « configurée / absente », jamais la valeur.

Duplique volontairement le petit chargeur de `.env` de `blogseo` (plutôt que
de l'importer) : la règle d'isolation interdit `pilotage` → `blogseo`, et ce
chargeur fait quinze lignes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..platforms import Platform

# `config/settings.py` → `pilotage` → `src` → racine du dépôt.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Même dossier que `BLOG_CONTENT_DIR` côté `blogseo` (voir .env.example section
# 6) : les deux systèmes lisent le même blog Next.js sur le même poste.
DEFAULT_BLOG_CONTENT_DIR = Path(
    "/home/oussama/Bureau/Chaine_youtube_Oussama_Dallel/Blog IA/oussama-blog/content/articles"
)
DEFAULT_PILOTAGE_DB_PATH = PROJECT_ROOT / "storage" / "pilotage" / "calendar.db"


def _load_dotenv() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        load_dotenv(env_file, override=False)
    except ImportError:  # pragma: no cover - repli sans dépendance
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _flag(value: str) -> str:
    return "✅ configurée" if value else "❌ absente"


@dataclass(frozen=True, slots=True)
class BotCredentials:
    """Token BotFather + chat_id d'un bot de pilotage, pour une plateforme."""

    platform: Platform
    bot_token: str = ""
    chat_id: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass(frozen=True, slots=True)
class BotsSettings:
    """Les six bots de pilotage. Un token absent désactive SON bot, pas les autres."""

    by_platform: dict[Platform, BotCredentials] = field(default_factory=dict)

    def for_platform(self, platform: Platform) -> BotCredentials:
        return self.by_platform[platform]

    @property
    def configured_platforms(self) -> tuple[Platform, ...]:
        return tuple(p for p, creds in self.by_platform.items() if creds.is_configured)


@dataclass(frozen=True, slots=True)
class CalendarSettings:
    db_path: Path = DEFAULT_PILOTAGE_DB_PATH
    blog_content_dir: Path = DEFAULT_BLOG_CONTENT_DIR


@dataclass(frozen=True, slots=True)
class YouTubeStatsSettings:
    api_key: str = ""
    channel_id: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.channel_id)


@dataclass(frozen=True, slots=True)
class MetaStatsSettings:
    """Facebook + Instagram, via un seul jeton de page (Meta Graph API)."""

    page_access_token: str = ""
    page_id: str = ""
    instagram_business_id: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.page_access_token and self.page_id)


@dataclass(frozen=True, slots=True)
class TelegramChannelStatsSettings:
    channel_username: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.channel_username)


@dataclass(frozen=True, slots=True)
class DashboardSettings:
    port: int = 8501


@dataclass(frozen=True, slots=True)
class PilotageSettings:
    bots: BotsSettings
    calendar: CalendarSettings
    youtube: YouTubeStatsSettings
    meta: MetaStatsSettings
    telegram_channel: TelegramChannelStatsSettings
    dashboard: DashboardSettings

    @classmethod
    def from_env(cls) -> PilotageSettings:
        _load_dotenv()

        bots = BotsSettings(
            by_platform={
                platform: BotCredentials(
                    platform=platform,
                    bot_token=_env(f"PILOTAGE_{platform.value.upper()}_BOT_TOKEN"),
                    chat_id=_env(f"PILOTAGE_{platform.value.upper()}_CHAT_ID"),
                )
                for platform in Platform.piloted()
            }
        )

        return cls(
            bots=bots,
            calendar=CalendarSettings(
                db_path=Path(_env("PILOTAGE_DB_PATH") or str(DEFAULT_PILOTAGE_DB_PATH)),
                blog_content_dir=Path(_env("BLOG_CONTENT_DIR") or str(DEFAULT_BLOG_CONTENT_DIR)),
            ),
            youtube=YouTubeStatsSettings(
                api_key=_env("YOUTUBE_API_KEY"),
                channel_id=_env("YOUTUBE_CHANNEL_ID"),
            ),
            meta=MetaStatsSettings(
                page_access_token=_env("META_PAGE_ACCESS_TOKEN"),
                page_id=_env("META_PAGE_ID"),
                instagram_business_id=_env("META_INSTAGRAM_BUSINESS_ID"),
            ),
            telegram_channel=TelegramChannelStatsSettings(
                channel_username=_env("TELEGRAM_CHANNEL_USERNAME"),
            ),
            dashboard=DashboardSettings(port=_env_int("DASHBOARD_PORT", 8501)),
        )

    def describe(self) -> str:
        """Résumé lisible, sans jamais afficher un token ou une clé."""
        lignes = ["  Bots de pilotage :"]
        for platform in Platform.piloted():
            creds = self.bots.for_platform(platform)
            lignes.append(f"    {platform.label:<24} {_flag(creds.bot_token)}")
        lignes += [
            f"  Calendrier      : {self.calendar.db_path}",
            f"  Dossier blog    : {self.calendar.blog_content_dir}",
            f"  YouTube stats   : clé {_flag(self.youtube.api_key)}",
            f"  Meta (FB/IG)    : jeton {_flag(self.meta.page_access_token)}",
            f"  Telegram canal  : {_flag(self.telegram_channel.channel_username)}",
            f"  Dashboard       : port {self.dashboard.port}",
        ]
        return "\n".join(lignes)
