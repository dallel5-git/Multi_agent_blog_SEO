"""Bot Telegram de pilotage Instagram (privé, usage personnel).

Token : `PILOTAGE_INSTAGRAM_BOT_TOKEN` · Chat : `PILOTAGE_INSTAGRAM_CHAT_ID`.
"""

from __future__ import annotations

from .handlers import create_bot

__all__ = ["create_bot"]
