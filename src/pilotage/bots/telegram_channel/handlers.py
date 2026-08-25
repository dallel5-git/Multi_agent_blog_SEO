"""Bot de pilotage du canal Telegram public.

⚠️ Ne pas confondre avec `TELEGRAM_BOT_TOKEN` (bot de validation du blog) ni
avec `TELEGRAM_CHANNEL_USERNAME` (le canal PUBLIC, cible de publication —
pas un outil). Ce bot-ci est privé : `PILOTAGE_TELEGRAM_CHANNEL_BOT_TOKEN` /
`_CHAT_ID` (CADRAGE.md risque n°5).

Toute la logique (commandes, boutons, garde `chat_id`) vit dans
`pilotage.bots.base.PilotageBot` — ce module ne fait que la brancher.
"""

from __future__ import annotations

from ...config.settings import PilotageSettings
from ...platforms import Platform
from ...shared_calendar.repository import CalendarRepository
from ..base import PilotageBot, create_bot_for_platform


def create_bot(settings: PilotageSettings, repository: CalendarRepository) -> PilotageBot:
    creds = settings.bots.for_platform(Platform.TELEGRAM_CHANNEL)
    return create_bot_for_platform(
        Platform.TELEGRAM_CHANNEL,
        token=creds.bot_token,
        chat_id=creds.chat_id,
        offset_path=settings.calendar.db_path.parent / "bot_offsets" / "telegram_channel.json",
        repository=repository,
    )
