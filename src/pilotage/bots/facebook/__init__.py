"""Bot Telegram de pilotage Facebook (privé, usage personnel).

Token : `PILOTAGE_FACEBOOK_BOT_TOKEN` · Chat : `PILOTAGE_FACEBOOK_CHAT_ID`.
"""

from __future__ import annotations

from .handlers import create_bot

__all__ = ["create_bot"]
