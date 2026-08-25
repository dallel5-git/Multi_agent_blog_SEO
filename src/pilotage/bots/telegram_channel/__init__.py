"""Bot Telegram de pilotage Telegram (canal) (privé, usage personnel).

Token : `PILOTAGE_TELEGRAM_CHANNEL_BOT_TOKEN` · Chat : `PILOTAGE_TELEGRAM_CHANNEL_CHAT_ID`.
"""

from __future__ import annotations

from .handlers import create_bot

__all__ = ["create_bot"]
