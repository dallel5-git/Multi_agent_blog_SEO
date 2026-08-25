"""Bot Telegram de pilotage TikTok (privé, usage personnel).

Token : `PILOTAGE_TIKTOK_BOT_TOKEN` · Chat : `PILOTAGE_TIKTOK_CHAT_ID`.
"""

from __future__ import annotations

from .handlers import create_bot

__all__ = ["create_bot"]
