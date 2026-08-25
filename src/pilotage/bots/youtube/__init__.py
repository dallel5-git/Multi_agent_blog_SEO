"""Bot Telegram de pilotage YouTube (privé, usage personnel).

Token : `PILOTAGE_YOUTUBE_BOT_TOKEN` · Chat : `PILOTAGE_YOUTUBE_CHAT_ID`.
"""

from __future__ import annotations

from .handlers import create_bot

__all__ = ["create_bot"]
