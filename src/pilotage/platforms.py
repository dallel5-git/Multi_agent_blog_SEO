"""Énumération des plateformes pilotées — seule constante partagée par tous les modules.

`Platform` est délibérément un `str, Enum` (même convention que `blogseo`,
voir la note `UP042` de `pyproject.toml`) : les valeurs sont sérialisées telles
quelles en base SQLite et dans les `callback_data` Telegram, puis reconstruites
par `Platform("youtube")`.

`BLOG` n'a **pas** de pipeline dans `pilotage/pipelines/` : les articles sont
produits par le système `blogseo` existant. Le blog figure ici uniquement pour
apparaître dans le calendrier partagé et pouvoir être la cible d'une mention
croisée.
"""

from __future__ import annotations

from enum import Enum


class Platform(str, Enum):
    """Les 6 plateformes pilotées, plus le blog en lecture seule."""

    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    X = "x"
    FACEBOOK = "facebook"
    TELEGRAM_CHANNEL = "telegram_channel"
    BLOG = "blog"

    @classmethod
    def piloted(cls) -> tuple[Platform, ...]:
        """Les 6 plateformes disposant d'un pipeline et d'un bot dédiés."""
        return tuple(p for p in cls if p is not cls.BLOG)

    @property
    def label(self) -> str:
        """Libellé lisible, affiché dans les bots et le tableau de bord."""
        return _LABELS[self]


_LABELS: dict[Platform, str] = {
    Platform.YOUTUBE: "YouTube",
    Platform.TIKTOK: "TikTok",
    Platform.INSTAGRAM: "Instagram",
    Platform.X: "X",
    Platform.FACEBOOK: "Facebook",
    Platform.TELEGRAM_CHANNEL: "Telegram (canal public)",
    Platform.BLOG: "Blog",
}
