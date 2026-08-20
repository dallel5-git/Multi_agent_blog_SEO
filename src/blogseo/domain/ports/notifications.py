"""Port `NotifierPort` : notifications et validation humaine (Telegram)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..entities.pipeline_run import Decision


class NotifierPort(ABC):
    """Canal de notification sortant."""

    name: str = "notifier"

    @abstractmethod
    def send(self, text: str, *, silent: bool = False) -> bool:
        """Envoie un message texte. Renvoie False en cas d'échec (jamais bloquant)."""

    @abstractmethod
    def send_document(self, path: Path, caption: str = "") -> bool:
        """Envoie un fichier en pièce jointe (utile pour le `.mdx` complet)."""

    def is_available(self) -> bool:
        return True


class HumanReviewPort(ABC):
    """Demande une décision humaine et attend la réponse.

    L'implémentation Telegram envoie un message avec des boutons inline puis
    interroge `getUpdates` jusqu'à recevoir un `callback_query` ou expirer.
    """

    @abstractmethod
    def request_decision(
        self,
        *,
        run_id: str,
        title: str,
        preview: str,
        document: Path | None = None,
        timeout_s: int = 86_400,
    ) -> Decision | None:
        """Renvoie la décision humaine, ou None en cas d'expiration du délai."""

    @abstractmethod
    def acknowledge(self, run_id: str, decision: Decision, detail: str = "") -> None:
        """Confirme à l'utilisateur que la décision a bien été exécutée."""
