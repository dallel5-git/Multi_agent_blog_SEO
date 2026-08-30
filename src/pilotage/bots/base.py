"""Socle commun des 6 bots de pilotage Telegram PRIVÉS.

Reprend l'approche déjà validée dans
`blogseo.infrastructure.notifications.telegram` (REST brut via `requests`,
pas d'asyncio, offset persisté) — **réimplémentée ici, pas importée** : la
règle d'isolation interdit à `pilotage` d'importer `blogseo`.

Différence structurante avec le bot du blog : celui-ci attend UNE décision
sur UN run puis s'arrête. Un bot de pilotage tourne en continu
(`run_forever()`) et route plusieurs commandes (`/en_attente`, `/stats`,
`/publie`, `/corrige`) plus les boutons inline ✅ ✏️ ❌, pour n'importe quel
nombre de contenus. C'est pourquoi toute la logique de commande vit ICI, dans
`PilotageBot` : les 6 modules `bots/<plateforme>/handlers.py` ne font que
brancher un token, un chat_id et un chemin d'offset — « ajouter un bot »
n'a rien d'autre à faire.

Les commandes `/en_attente`, `/stats` et les boutons sont volontairement
IDENTIQUES d'une plateforme à l'autre (mêmes descriptions dans les 6 issues
GitHub) : seule la donnée change, filtrée par `self.platform`.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

from ..platforms import Platform
from ..shared_calendar.models import ContentStatus, PlatformPost
from ..shared_calendar.repository import CalendarRepository
from ..stats_collector.manual_entry import posts_needing_manual_entry, record_manual_measurement

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
_CALLBACK_PREFIX = "pilotage"

#: Clavier persistant affiché au démarrage du bot quand une génération à la
#: demande est câblée (voir `PilotageBot.generate_callback`) — un appui envoie
#: le texte "/generer", routé comme n'importe quelle commande tapée.
_GENERATE_KEYBOARD = {
    "keyboard": [[{"text": "/generer"}]],
    "resize_keyboard": True,
    "is_persistent": True,
}


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class TelegramApiError(Exception):
    """Erreur Telegram (`ok: false`) ou panne réseau après épuisement des tentatives."""


@dataclass(frozen=True, slots=True)
class BotConfig:
    platform: Platform
    token: str
    chat_id: str
    offset_path: Path
    poll_interval_s: int = 5
    timeout_s: int = 30


class PilotageBot:
    """Bot Telegram privé d'une plateforme.

    Garde stricte : ne répond jamais à un `chat_id` autre que
    `config.chat_id` — ces bots sont personnels, pas des bots publics.
    """

    def __init__(
        self,
        config: BotConfig,
        repository: CalendarRepository,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self._session = session or requests.Session()
        self.logger = logging.getLogger(f"pilotage.bots.{config.platform.value}")
        #: Câblé par `cli._make_bot()` vers `pipeline.run()` — laissé à `None`
        #: par le socle pour ne pas coupler `bots` à `pipelines` ici.
        self.generate_callback: Callable[[], int] | None = None

    @property
    def platform(self) -> Platform:
        return self.config.platform

    def is_configured(self) -> bool:
        return bool(self.config.token and self.config.chat_id)

    # ------------------------------------------------------------------ #
    # Appels bas niveau — retry avec backoff exponentiel
    # ------------------------------------------------------------------ #
    def _call(self, method: str, payload: dict | None = None, *, timeout: int | None = None) -> dict:
        url = _API.format(token=self.config.token, method=method)
        delay = 1.0
        derniere_erreur: Exception | None = None
        for tentative in range(3):
            try:
                response = self._session.post(url, json=payload or {}, timeout=timeout or self.config.timeout_s)
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                derniere_erreur = exc
                self.logger.warning(
                    "%s a échoué (tentative %s/3) : %s", method, tentative + 1, exc
                )
                time.sleep(delay)
                delay *= 2
                continue
            if not data.get("ok"):
                raise TelegramApiError(f"{method} → {data.get('description', 'erreur inconnue')}")
            return data.get("result", {})
        raise TelegramApiError(f"{method} injoignable après 3 tentatives : {derniere_erreur}")

    def send_message(self, text: str, *, reply_markup: dict | None = None) -> None:
        payload: dict = {
            "chat_id": self.config.chat_id,
            "text": _truncate(text, 4000),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            self._call("sendMessage", payload)
        except TelegramApiError as exc:
            self.logger.error("Message non envoyé : %s", exc)

    # ------------------------------------------------------------------ #
    # Offset `getUpdates` — persisté, jamais rejoué au redémarrage
    # ------------------------------------------------------------------ #
    def _load_offset(self) -> int:
        if not self.config.offset_path.exists():
            return 0
        try:
            return int(json.loads(self.config.offset_path.read_text(encoding="utf-8")).get("offset", 0))
        except (OSError, ValueError, TypeError):
            return 0

    def _save_offset(self, offset: int) -> None:
        try:
            self.config.offset_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.offset_path.write_text(json.dumps({"offset": offset}), encoding="utf-8")
        except OSError:  # pragma: no cover - défensif
            pass

    # ------------------------------------------------------------------ #
    # Boucle
    # ------------------------------------------------------------------ #
    def poll_once(self, *, poll_timeout: int = 25) -> int:
        """Un tour de `getUpdates`. Renvoie le nombre de mises à jour traitées.

        Séparé de `run_forever()` pour rester testable sans boucle infinie.
        """
        offset = self._load_offset()
        try:
            updates = self._call(
                "getUpdates",
                {"offset": offset, "timeout": poll_timeout, "allowed_updates": ["message", "callback_query"]},
                timeout=poll_timeout + 15,
            )
        except TelegramApiError as exc:
            self.logger.warning("getUpdates indisponible : %s", exc)
            return 0

        traitees = 0
        for update in updates:
            self._save_offset(update["update_id"] + 1)
            if self._handle_update(update):
                traitees += 1
        return traitees

    def run_forever(self) -> None:
        if not self.is_configured():
            self.logger.warning(
                "Bot %s non configuré (token/chat_id manquant) — arrêt.", self.platform.value
            )
            return
        self.logger.info("▶ Bot %s en écoute", self.platform.value)
        if self.generate_callback is not None:
            self.send_message(
                "🎬 Bot de pilotage prêt. Appuyez sur le bouton pour générer un nouveau script.",
                reply_markup=_GENERATE_KEYBOARD,
            )
        while True:
            self.poll_once()

    # ------------------------------------------------------------------ #
    # Routage
    # ------------------------------------------------------------------ #
    def _authorized(self, chat_id: object) -> bool:
        autorise = str(chat_id) == self.config.chat_id
        if not autorise:
            self.logger.warning(
                "Message %s ignoré : chat_id %s non autorisé", self.platform.value, chat_id
            )
        return autorise

    def _handle_update(self, update: dict) -> bool:
        if "callback_query" in update:
            return self._handle_callback(update["callback_query"])
        if "message" in update:
            return self._handle_message(update["message"])
        return False

    def _handle_message(self, message: dict) -> bool:
        if not self._authorized(message.get("chat", {}).get("id")):
            return False
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return False

        commande, *arguments = text.split()
        commande = commande.split("@")[0]  # /commande@NomDuBot → /commande

        routes = {
            "/generer": lambda: self._cmd_generer(),
            "/en_attente": lambda: self._cmd_en_attente(),
            "/stats": lambda: self._cmd_stats(),
            "/publie": lambda: self._cmd_publie(arguments),
            "/corrige": lambda: self._cmd_corrige(arguments),
            "/rappel_stats": lambda: self._cmd_rappel_stats(),
            "/mesure": lambda: self._cmd_mesure(arguments),
            "/passe": lambda: self._cmd_passe(arguments),
        }
        handler = routes.get(commande)
        if handler is None:
            return False
        handler()
        return True

    def _handle_callback(self, query: dict) -> bool:
        message = query.get("message", {})
        if not self._authorized(message.get("chat", {}).get("id")):
            return False

        data = query.get("data", "")
        parts = data.split(":", 2)
        if len(parts) != 3 or parts[0] != _CALLBACK_PREFIX:
            return False
        _, item_id_str, action = parts
        try:
            item_id = int(item_id_str)
        except ValueError:
            return False

        item = self.repository.get_item(item_id)
        if item is None or item.platform is not self.platform:
            # Jamais d'action sur le contenu d'une autre plateforme.
            self._answer_callback(query["id"], "Contenu introuvable pour ce bot.")
            return False

        reponse = self._apply_decision(item_id, action)
        if reponse is None:
            return False

        self._answer_callback(query["id"], reponse)
        self._remove_keyboard(message)
        self.send_message(reponse)
        return True

    def _apply_decision(self, item_id: int, action: str) -> str | None:
        if action == "approve":
            self.repository.update_status(item_id, ContentStatus.APPROVED)
            return f"✅ #{item_id} validé — utilise /publie <lien> une fois publié."
        if action == "reject":
            self.repository.update_status(item_id, ContentStatus.REJECTED)
            return f"❌ #{item_id} rejeté."
        if action == "edit":
            self.repository.update_status(item_id, ContentStatus.DRAFTED)
            return f"✏️ #{item_id} renvoyé au rédacteur. /corrige {item_id} <ton retour> pour préciser."
        return None

    def _answer_callback(self, callback_query_id: str, text: str) -> None:
        try:
            self._call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text[:200]})
        except TelegramApiError as exc:
            self.logger.debug("answerCallbackQuery a échoué : %s", exc)

    def _remove_keyboard(self, message: dict) -> None:
        """Empêche un double clic : le clavier disparaît après la première décision."""
        if not message:
            return
        try:
            self._call("editMessageReplyMarkup", {
                "chat_id": message["chat"]["id"],
                "message_id": message["message_id"],
                "reply_markup": {"inline_keyboard": []},
            })
        except TelegramApiError as exc:
            self.logger.debug("Retrait du clavier a échoué : %s", exc)

    # ------------------------------------------------------------------ #
    # Commandes
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decision_keyboard(item_id: int) -> dict:
        return {
            "inline_keyboard": [[
                {"text": "✅", "callback_data": f"{_CALLBACK_PREFIX}:{item_id}:approve"},
                {"text": "✏️", "callback_data": f"{_CALLBACK_PREFIX}:{item_id}:edit"},
                {"text": "❌", "callback_data": f"{_CALLBACK_PREFIX}:{item_id}:reject"},
            ]]
        }

    def notify_pending_drafts(self) -> int:
        """Envoie chaque brouillon fraîchement écrit (`status='drafted'`) avec
        son clavier de décision, et le fait passer à `pending_review`.

        C'est la transition `drafted → pending_review: envoyé au bot
        Telegram` du cycle de vie (ARCHITECTURE.md §4) : `submit()` du
        pipeline (lot 3) persiste en `drafted` sans jamais parler à
        Telegram — un pipeline ne doit pas échouer si le bot n'est pas
        configuré. C'est ici, côté bot, que le brouillon est effectivement
        envoyé pour revue. Renvoie le nombre de brouillons envoyés.
        """
        drafts = [
            item for item in self.repository.list_by_platform(self.platform)
            if item.status is ContentStatus.DRAFTED
        ]
        for item in drafts:
            self.send_message(
                f"<b>#{item.id} — {item.title}</b>\n\n{_truncate(item.body or '', 3500)}",
                reply_markup=self._decision_keyboard(item.id),
            )
            self.repository.update_status(item.id, ContentStatus.PENDING_REVIEW)
        return len(drafts)

    def _cmd_generer(self) -> None:
        """Déclenche une génération à la demande (bouton ou `/generer` tapé) :
        lance le pipeline câblé par `cli._make_bot()`, puis envoie le
        brouillon obtenu avec son clavier de décision, comme le ferait le
        déclenchement planifié (`pilotage run <plateforme>`)."""
        if self.generate_callback is None:
            self.send_message("Génération à la demande non disponible pour ce bot.")
            return
        self.send_message("⏳ Génération d'un nouveau script en cours (jusqu'à une minute)…")
        try:
            self.generate_callback()
        except Exception as exc:  # noqa: BLE001 - ne doit jamais interrompre la boucle du bot
            self.logger.error("Génération à la demande en échec : %s", exc)
            self.send_message(f"✖ Génération impossible : {exc}")
            return
        if self.notify_pending_drafts() == 0:
            self.send_message("Génération terminée, mais rien à envoyer (déjà en attente ?).")

    def _cmd_en_attente(self) -> None:
        """Reliste ce qui attend déjà une décision (`pending_review`) — pour
        pousser les brouillons tout juste écrits, voir `notify_pending_drafts()`."""
        items = [
            item for item in self.repository.list_by_platform(self.platform)
            if item.status is ContentStatus.PENDING_REVIEW
        ]
        if not items:
            self.send_message("Rien en attente pour l'instant.")
            return
        for item in items:
            self.send_message(
                f"<b>#{item.id} — {item.title}</b>\n\n{_truncate(item.body or '', 3500)}",
                reply_markup=self._decision_keyboard(item.id),
            )

    def _cmd_stats(self) -> None:
        posts = [
            post for post in self.repository.list_recent_posts(limit=100)
            if post.platform is self.platform
        ][:5]
        if not posts:
            self.send_message("Aucune publication enregistrée pour l'instant.")
            return

        lignes = []
        for post in posts:
            snapshot = self.repository.latest_snapshot(post.id)
            if snapshot is None:
                lignes.append(f"• {post.url} — aucune mesure")
            else:
                lignes.append(
                    f"• {post.url} — {snapshot.views or 0} vues, {snapshot.likes or 0} likes "
                    f"({snapshot.source.value})"
                )
        self.send_message("<b>Dernières statistiques :</b>\n" + "\n".join(lignes))

    def _cmd_publie(self, arguments: list[str]) -> None:
        if not arguments:
            self.send_message("Usage : /publie <lien>  (ou /publie <id> <lien>)")
            return

        if len(arguments) >= 2 and arguments[0].isdigit():
            item_id = int(arguments[0])
            url = arguments[1]
        else:
            url = arguments[0]
            candidats = [
                item for item in self.repository.list_by_platform(self.platform)
                if item.status is ContentStatus.APPROVED
            ]
            if not candidats:
                self.send_message("Aucun contenu approuvé en attente de publication pour l'instant.")
                return
            # Le plus ancien approuvé d'abord (FIFO).
            item_id = min(candidats, key=lambda item: item.created_at or "").id

        try:
            self.repository.add_post(
                PlatformPost(
                    content_item_id=item_id,
                    platform=self.platform,
                    url=url,
                    published_at=date.today().isoformat(),
                )
            )
        except sqlite3.IntegrityError:
            self.send_message("Ce lien est déjà enregistré.")
            return

        self.repository.update_status(item_id, ContentStatus.PUBLISHED)
        self.send_message(f"🚀 Publication enregistrée pour #{item_id} : {url}")

    def _cmd_corrige(self, arguments: list[str]) -> None:
        if len(arguments) < 2 or not arguments[0].isdigit():
            self.send_message("Usage : /corrige <id> <ton retour>")
            return

        item_id = int(arguments[0])
        item = self.repository.get_item(item_id)
        if item is None or item.platform is not self.platform:
            self.send_message("Contenu introuvable pour ce bot.")
            return

        feedback = " ".join(arguments[1:])
        self.repository.update_body(item_id, f"[CORRECTION DEMANDÉE : {feedback}]\n\n{item.body or ''}")
        self.send_message(f"✏️ Retour enregistré pour #{item_id}.")

    # ------------------------------------------------------------------ #
    # Rappel hebdomadaire de saisie manuelle (TikTok, X — CADRAGE.md risque n°4)
    #
    # Le déclenchement périodique (STATS_MANUAL_REMINDER_CRON) n'est PAS géré
    # ici : ce module n'ouvre aucune boucle de planification. Un timer
    # systemd ou un cron externe appelle `pilotage remind-stats <plateforme>`
    # (voir cli.py), sur le modèle de `scripts/install_systemd_timer.sh`.
    #
    # Une question à la fois, jamais un formulaire : le rappel liste les
    # publications concernées avec leur id, l'auteur répond au fil de l'eau
    # avec `/mesure <id> <vues> [likes]` ou `/passe <id>` (lot 5, risque n°4).
    # ------------------------------------------------------------------ #
    def compose_manual_stats_reminder(self) -> str | None:
        posts = posts_needing_manual_entry(self.repository, self.platform)
        if not posts:
            return None
        lignes = "\n".join(f"• #{post.id} — {post.url}" for post in posts)
        return (
            "📊 Rappel — aucune mesure saisie pour :\n"
            f"{lignes}\n\n"
            "Réponds publication par publication : /mesure <id> <vues> [likes], "
            "ou /passe <id> pour ignorer celle-ci sans bloquer les autres."
        )

    def send_manual_stats_reminder(self) -> None:
        message = self.compose_manual_stats_reminder()
        if message is not None:
            self.send_message(message)

    def _cmd_rappel_stats(self) -> None:
        message = self.compose_manual_stats_reminder()
        self.send_message(message or "Rien à rappeler : toutes les publications ont une mesure récente.")

    def _cmd_mesure(self, arguments: list[str]) -> None:
        if len(arguments) < 2 or not arguments[0].isdigit() or not arguments[1].isdigit():
            self.send_message("Usage : /mesure <id> <vues> [likes]")
            return

        post_id = int(arguments[0])
        views = int(arguments[1])
        likes = int(arguments[2]) if len(arguments) >= 3 and arguments[2].isdigit() else None

        record_manual_measurement(
            self.repository, platform_post_id=post_id, platform=self.platform, views=views, likes=likes
        )
        self.send_message(f"✅ Mesure enregistrée pour #{post_id} ({views} vues).")

    def _cmd_passe(self, arguments: list[str]) -> None:
        if not arguments or not arguments[0].isdigit():
            self.send_message("Usage : /passe <id>")
            return
        self.send_message(f"⏭ #{arguments[0]} ignoré pour cette fois — repassera au prochain rappel.")


def create_bot_for_platform(
    platform: Platform,
    *,
    token: str,
    chat_id: str,
    offset_path: Path,
    repository: CalendarRepository,
) -> PilotageBot:
    """Fabrique commune aux 6 `bots/<plateforme>/handlers.py` — chacun ne
    fait que fournir ses propres identifiants, rien d'autre à modifier ici."""
    config = BotConfig(platform=platform, token=token, chat_id=chat_id, offset_path=offset_path)
    return PilotageBot(config, repository)


__all__ = [
    "BotConfig",
    "PilotageBot",
    "TelegramApiError",
    "create_bot_for_platform",
]
