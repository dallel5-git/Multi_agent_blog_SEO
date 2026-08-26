"""Collecteur Telegram (canal public) — nombre d'abonnés via `getChatMemberCount`.

CADRAGE.md décision 13, tranchée : on se limite au nombre d'abonnés (mesure
de compte, `platform_post_id = NULL`). Telegram n'expose pas les vues par
message à un bot ; les saisir à la main ajouterait une TROISIÈME saisie
manuelle (après X et TikTok, risque n°4), pour un bénéfice qui ne semble pas
proportionné tant qu'aucun besoin réel ne l'a démontré. Décision révisable
avec l'auteur si ce besoin apparaît — voir CADRAGE.md.

Utilise le token du bot de pilotage `telegram_channel`
(`PILOTAGE_TELEGRAM_CHANNEL_BOT_TOKEN`) : ce bot doit être ADMINISTRATEUR du
canal pour que `getChatMemberCount` réponde.
"""

from __future__ import annotations

from datetime import date

import requests

from ..platforms import Platform
from ..shared_calendar.models import StatSnapshot, StatSource
from ..shared_calendar.repository import CalendarRepository
from .base import StatsCollector

_TIMEOUT_S = 20
_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramChannelStatsCollector(StatsCollector):
    platform = Platform.TELEGRAM_CHANNEL

    def __init__(self, repository: CalendarRepository, *, bot_token: str, channel_username: str) -> None:
        super().__init__(repository)
        self.bot_token = bot_token
        self.channel_username = channel_username

    def collect(self, since: date) -> list[StatSnapshot]:
        if not (self.bot_token and self.channel_username):
            self.logger.info(
                "PILOTAGE_TELEGRAM_CHANNEL_BOT_TOKEN / TELEGRAM_CHANNEL_USERNAME "
                "absent(s) — collecte ignorée."
            )
            return []

        chat = self.channel_username if self.channel_username.startswith("@") else f"@{self.channel_username}"
        url = _API.format(token=self.bot_token, method="getChatMemberCount")

        try:
            response = requests.get(url, params={"chat_id": chat}, timeout=_TIMEOUT_S)
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            self.logger.warning("Telegram Bot API injoignable : %s", exc)
            return []

        if not payload.get("ok"):
            description = payload.get("description", "erreur inconnue")
            if "administrator" in description.lower() or "not enough rights" in description.lower():
                self.logger.warning(
                    "Le bot de pilotage n'est pas administrateur du canal %s : %s", chat, description
                )
            else:
                self.logger.warning("getChatMemberCount → %s", description)
            return []

        return [
            StatSnapshot(
                platform=Platform.TELEGRAM_CHANNEL,
                platform_post_id=None,  # mesure de compte
                source=StatSource.API,
                followers=payload.get("result"),
            )
        ]
