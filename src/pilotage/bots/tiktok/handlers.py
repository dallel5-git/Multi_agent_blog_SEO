"""Bot de pilotage TikTok.

Toute la logique (commandes, boutons, garde `chat_id`) vit dans
`pilotage.bots.base.PilotageBot` — ce module ne fait que la brancher sur les
identifiants TikTok (`PILOTAGE_TIKTOK_BOT_TOKEN` / `_CHAT_ID`).

⚠️ Pas d'API d'engagement gratuite pour cette plateforme : ce bot est aussi
celui qui porte `send_manual_stats_reminder()` (voir `pilotage remind-stats`),
déclenché par un cron externe (`STATS_MANUAL_REMINDER_CRON`).
"""

from __future__ import annotations

from ...config.settings import PilotageSettings
from ...platforms import Platform
from ...shared_calendar.repository import CalendarRepository
from ..base import PilotageBot, create_bot_for_platform


def create_bot(settings: PilotageSettings, repository: CalendarRepository) -> PilotageBot:
    creds = settings.bots.for_platform(Platform.TIKTOK)
    return create_bot_for_platform(
        Platform.TIKTOK,
        token=creds.bot_token,
        chat_id=creds.chat_id,
        offset_path=settings.calendar.db_path.parent / "bot_offsets" / "tiktok.json",
        repository=repository,
    )
