"""Bot de pilotage Facebook.

Toute la logique (commandes, boutons, garde `chat_id`) vit dans
`pilotage.bots.base.PilotageBot` — ce module ne fait que la brancher sur les
identifiants Facebook (`PILOTAGE_FACEBOOK_BOT_TOKEN` / `_CHAT_ID`).
"""

from __future__ import annotations

from ...config.settings import PilotageSettings
from ...platforms import Platform
from ...shared_calendar.repository import CalendarRepository
from ..base import PilotageBot, create_bot_for_platform


def create_bot(settings: PilotageSettings, repository: CalendarRepository) -> PilotageBot:
    creds = settings.bots.for_platform(Platform.FACEBOOK)
    return create_bot_for_platform(
        Platform.FACEBOOK,
        token=creds.bot_token,
        chat_id=creds.chat_id,
        offset_path=settings.calendar.db_path.parent / "bot_offsets" / "facebook.json",
        repository=repository,
    )
