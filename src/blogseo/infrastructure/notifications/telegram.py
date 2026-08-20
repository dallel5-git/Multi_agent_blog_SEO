"""Bot Telegram : notifications + validation humaine à boutons.

Contrat métier voulu par l'auteur :
- ✅ **Publier** → l'article est écrit dans `content/articles/`, commité et
  poussé sur GitHub → Vercel déploie automatiquement ;
- ❌ **Garder en local** → l'article est seulement écrit dans
  `content/articles/` ; c'est l'auteur qui fait le `git push` après relecture ;
- 🔁 **Réécrire** → l'article repart au Content Writer avec un feedback.

Implémentation en REST brut (`requests`) sur la Bot API : pas de dépendance
`python-telegram-bot`, pas d'`asyncio`, et un long-polling `getUpdates` simple à
raisonner. `offset` est persisté pour ne jamais rejouer un vieux callback.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

from ...domain.entities.pipeline_run import Decision
from ...domain.errors import NotificationError
from ...domain.ports.notifications import HumanReviewPort, NotifierPort
from ...shared.text import truncate

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"

#: Préfixe des `callback_data` : `blogseo:<run_id>:<decision>`
_CALLBACK_PREFIX = "blogseo"


class TelegramBot(NotifierPort, HumanReviewPort):
    """Notifier + porte de validation humaine, dans un seul adapter."""

    name = "telegram"

    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        state_dir: Path | None = None,
        poll_interval_s: int = 5,
        timeout_s: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.token = token
        self.chat_id = str(chat_id)
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s
        self._session = session or requests.Session()
        self._offset_file = (state_dir / "telegram_offset.json") if state_dir else None

    def is_available(self) -> bool:
        return bool(self.token and self.chat_id)

    # ------------------------------------------------------------------ #
    # Appels bas niveau
    # ------------------------------------------------------------------ #
    def _call(self, method: str, payload: dict | None = None, *, files: dict | None = None,
              timeout: int | None = None) -> dict:
        if not self.is_available():
            raise NotificationError("Telegram non configuré (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        url = _API.format(token=self.token, method=method)
        try:
            if files:
                response = self._session.post(url, data=payload or {}, files=files,
                                              timeout=timeout or self.timeout_s)
            else:
                response = self._session.post(url, json=payload or {},
                                              timeout=timeout or self.timeout_s)
        except requests.RequestException as exc:
            raise NotificationError(f"Telegram injoignable : {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise NotificationError(f"Réponse Telegram non JSON : {response.text[:200]}") from exc

        if not data.get("ok"):
            raise NotificationError(f"Telegram {method} → {data.get('description', 'erreur inconnue')}")
        return data.get("result", {})

    # ------------------------------------------------------------------ #
    # NotifierPort
    # ------------------------------------------------------------------ #
    def send(self, text: str, *, silent: bool = False) -> bool:
        try:
            self._call("sendMessage", {
                "chat_id": self.chat_id,
                "text": truncate(text, 4000),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "disable_notification": silent,
            })
            return True
        except NotificationError as exc:
            logger.error("Notification Telegram non envoyée : %s", exc)
            return False

    def send_document(self, path: Path, caption: str = "") -> bool:
        if not path.exists():
            logger.warning("Document introuvable : %s", path)
            return False
        try:
            with path.open("rb") as handle:
                self._call(
                    "sendDocument",
                    {"chat_id": self.chat_id, "caption": truncate(caption, 1000), "parse_mode": "HTML"},
                    files={"document": (path.name, handle)},
                    timeout=120,
                )
            return True
        except NotificationError as exc:
            logger.error("Document Telegram non envoyé : %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # HumanReviewPort
    # ------------------------------------------------------------------ #
    def request_decision(
        self,
        *,
        run_id: str,
        title: str,
        preview: str,
        document: Path | None = None,
        timeout_s: int = 86_400,
    ) -> Decision | None:
        """Envoie l'aperçu + les boutons, puis attend le clic (long-polling)."""
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Publier (push Git)",
                     "callback_data": f"{_CALLBACK_PREFIX}:{run_id}:{Decision.APPROVE.value}"},
                ],
                [
                    {"text": "❌ Garder en local",
                     "callback_data": f"{_CALLBACK_PREFIX}:{run_id}:{Decision.REJECT.value}"},
                ],
                [
                    {"text": "🔁 Faire réécrire",
                     "callback_data": f"{_CALLBACK_PREFIX}:{run_id}:{Decision.REWRITE.value}"},
                ],
            ]
        }

        try:
            self._call("sendMessage", {
                "chat_id": self.chat_id,
                "text": preview,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": keyboard,
            })
        except NotificationError as exc:
            logger.error("Impossible d'envoyer la demande de validation : %s", exc)
            return None

        if document is not None:
            self.send_document(document, caption=f"📄 Article complet — {truncate(title, 200)}")

        return self._wait_for_callback(run_id, timeout_s)

    def _wait_for_callback(self, run_id: str, timeout_s: int) -> Decision | None:
        deadline = time.monotonic() + timeout_s
        offset = self._load_offset()
        logger.info(
            "En attente de votre décision Telegram pour le run %s (délai max : %s h)…",
            run_id, round(timeout_s / 3600, 1),
        )

        while time.monotonic() < deadline:
            remaining = int(deadline - time.monotonic())
            # `timeout` du long-polling côté serveur Telegram : jusqu'à 50 s.
            poll_timeout = max(1, min(50, remaining))
            try:
                updates = self._call(
                    "getUpdates",
                    {"offset": offset, "timeout": poll_timeout,
                     "allowed_updates": ["callback_query", "message"]},
                    timeout=poll_timeout + 15,
                )
            except NotificationError as exc:
                logger.warning("getUpdates a échoué (%s) — nouvelle tentative", exc)
                time.sleep(self.poll_interval_s)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                self._save_offset(offset)
                decision = self._decision_from_update(update, run_id)
                if decision is not None:
                    logger.info("Décision reçue pour le run %s : %s", run_id, decision.value)
                    return decision

        logger.warning("Aucune décision reçue pour le run %s dans le délai imparti", run_id)
        return None

    def _decision_from_update(self, update: dict, run_id: str) -> Decision | None:
        query = update.get("callback_query")
        if not query:
            return None
        data = query.get("data", "")
        parts = data.split(":")
        if len(parts) != 3 or parts[0] != _CALLBACK_PREFIX or parts[1] != run_id:
            return None

        try:
            decision = Decision(parts[2])
        except ValueError:
            return None

        labels = {
            Decision.APPROVE: "✅ Publication en cours…",
            Decision.REJECT: "❌ Enregistrement local…",
            Decision.REWRITE: "🔁 Réécriture demandée…",
        }
        try:
            self._call("answerCallbackQuery", {
                "callback_query_id": query["id"],
                "text": labels[decision],
            })
            # On retire le clavier pour empêcher un double clic.
            message = query.get("message", {})
            if message:
                self._call("editMessageReplyMarkup", {
                    "chat_id": message["chat"]["id"],
                    "message_id": message["message_id"],
                    "reply_markup": {"inline_keyboard": []},
                })
        except NotificationError as exc:  # non bloquant
            logger.debug("Accusé de réception Telegram partiel : %s", exc)

        return decision

    def acknowledge(self, run_id: str, decision: Decision, detail: str = "") -> None:
        icons = {Decision.APPROVE: "🚀", Decision.REJECT: "💾", Decision.REWRITE: "🔁"}
        self.send(f"{icons.get(decision, 'ℹ️')} <b>Run {run_id}</b>\n{detail}")

    # ------------------------------------------------------------------ #
    def _load_offset(self) -> int:
        if not self._offset_file or not self._offset_file.exists():
            return 0
        try:
            return int(json.loads(self._offset_file.read_text(encoding="utf-8")).get("offset", 0))
        except (OSError, ValueError, TypeError):
            return 0

    def _save_offset(self, offset: int) -> None:
        if not self._offset_file:
            return
        try:
            self._offset_file.parent.mkdir(parents=True, exist_ok=True)
            self._offset_file.write_text(json.dumps({"offset": offset}), encoding="utf-8")
        except OSError:  # pragma: no cover - défensif
            pass


class NullNotifier(NotifierPort, HumanReviewPort):
    """Notifier neutre utilisé quand Telegram n'est pas configuré ou en dry-run.

    En l'absence de canal de validation, on retombe sur la décision la plus sûre :
    ne rien publier automatiquement (`Decision.REJECT` = écriture locale seule).
    """

    name = "null-notifier"

    def __init__(self, *, default_decision: Decision = Decision.REJECT) -> None:
        self.default_decision = default_decision
        self.messages: list[str] = []

    def is_available(self) -> bool:
        return False

    def send(self, text: str, *, silent: bool = False) -> bool:
        self.messages.append(text)
        logger.info("[notification simulée] %s", truncate(text.replace("\n", " "), 300))
        return True

    def send_document(self, path: Path, caption: str = "") -> bool:
        logger.info("[document simulé] %s", path)
        return True

    def request_decision(self, *, run_id, title, preview, document=None, timeout_s=86_400) -> Decision | None:
        logger.warning(
            "Telegram non configuré : décision par défaut « %s » appliquée au run %s",
            self.default_decision.value, run_id,
        )
        return self.default_decision

    def acknowledge(self, run_id: str, decision: Decision, detail: str = "") -> None:
        logger.info("[accusé simulé] run %s → %s : %s", run_id, decision.value, detail)
