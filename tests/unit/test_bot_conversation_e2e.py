"""Test bout-en-bout d'une conversation de bot de pilotage (Lot 7, issue #83).

Rejoue le scénario complet : brouillon produit par un pipeline réel (hors
ligne) → envoyé pour revue → ✅ validé → `/publie [lien]` → publication
enregistrée → mesure collectée. Le transport Telegram est remplacé par
`FakeSession` (le « double de test » demandé par l'issue) : `requests` n'est
jamais importé par ce fichier, aucun appel ne peut donc atteindre
`api.telegram.org` — la substitution du transport le garantit par
construction, pas seulement par convention.

Les trois décisions (✅ / ✏️ / ❌) sont chacune rejouées dans un test dédié,
sur le modèle des scénarios déjà couverts dans `test_bots.py` — ici assemblées
en une seule histoire cohérente plutôt qu'en unités isolées.
"""

from __future__ import annotations

from pilotage.bots.base import BotConfig, PilotageBot
from pilotage.pipelines.youtube import YouTubePipeline
from pilotage.platforms import Platform
from pilotage.shared.llm import FakeLLM
from pilotage.shared_calendar.models import ContentStatus, StatSnapshot, StatSource

_CHAT_ID = "12345"
_AUTRE_CHAT_ID = "00000"


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Double de test du transport Telegram : encaisse les appels, sert des
    lots d'`updates` prédéfinis. Aucun réseau, aucune dépendance à `requests`."""

    def __init__(self, updates_batches: list[list[dict]] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._updates_batches = list(updates_batches or [])

    def post(self, url, *, json=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json or {}))
        if method == "getUpdates":
            batch = self._updates_batches.pop(0) if self._updates_batches else []
            return FakeResponse({"ok": True, "result": batch})
        return FakeResponse({"ok": True, "result": {}})

    def calls_for(self, method: str) -> list[dict]:
        return [payload for name, payload in self.calls if name == method]


def _message(update_id: int, text: str, *, chat_id: str = _CHAT_ID) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


def _callback(update_id: int, item_id: int, action: str, *, chat_id: str = _CHAT_ID) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cbq{update_id}",
            "data": f"pilotage:{item_id}:{action}",
            "message": {"chat": {"id": chat_id}, "message_id": 1},
        },
    }


def _bot(session: FakeSession, calendar_repository, tmp_path) -> PilotageBot:
    config = BotConfig(
        platform=Platform.YOUTUBE, token="fake-token", chat_id=_CHAT_ID,
        offset_path=tmp_path / "offset.json", timeout_s=5,
    )
    return PilotageBot(config, calendar_repository, session=session)


def _produce_draft(calendar_repository, brand_kernel) -> int:
    """Étape 1 : un vrai pipeline, hors ligne, produit le brouillon."""
    pipeline = YouTubePipeline(
        repository=calendar_repository, brand_kernel=brand_kernel, llm=FakeLLM(), offline=True
    )
    return pipeline.run()


# --------------------------------------------------------------------------- #
# Scénario complet : brouillon → envoi → ✅ → /publie → mesure
# --------------------------------------------------------------------------- #
def test_scenario_complet_brouillon_valide_puis_publie_puis_mesure(
    calendar_repository, brand_kernel, tmp_path
):
    item_id = _produce_draft(calendar_repository, brand_kernel)
    assert calendar_repository.get_item(item_id).status is ContentStatus.DRAFTED

    # Étape 2 : le bot envoie le brouillon pour revue (drafted → pending_review).
    session = FakeSession()
    bot = _bot(session, calendar_repository, tmp_path)
    envoyes = bot.notify_pending_drafts()

    assert envoyes == 1
    assert calendar_repository.get_item(item_id).status is ContentStatus.PENDING_REVIEW
    premier_envoi = session.calls_for("sendMessage")[0]
    assert f"#{item_id}" in premier_envoi["text"]
    assert premier_envoi["reply_markup"]["inline_keyboard"]

    # Étape 3 : ✅ validé.
    session_validation = FakeSession(updates_batches=[[_callback(1, item_id, "approve")]])
    bot_validation = _bot(session_validation, calendar_repository, tmp_path)
    bot_validation.poll_once()

    assert calendar_repository.get_item(item_id).status is ContentStatus.APPROVED
    assert session_validation.calls_for("editMessageReplyMarkup")[0]["reply_markup"]["inline_keyboard"] == []

    # Étape 4 : /publie [lien].
    session_publication = FakeSession(
        updates_batches=[[_message(2, "/publie https://youtu.be/e2e-test")]]
    )
    bot_publication = _bot(session_publication, calendar_repository, tmp_path)
    bot_publication.poll_once()

    assert calendar_repository.get_item(item_id).status is ContentStatus.PUBLISHED
    posts = calendar_repository.list_recent_posts()
    assert posts[0].url == "https://youtu.be/e2e-test"

    # Étape 5 : une mesure est collectée (manuellement, comme le ferait /mesure).
    calendar_repository.add_snapshot(
        StatSnapshot(
            platform=Platform.YOUTUBE, platform_post_id=posts[0].id,
            source=StatSource.API, views=42,
        )
    )
    mesure = calendar_repository.latest_snapshot(posts[0].id)
    assert mesure is not None
    assert mesure.views == 42


def test_publie_en_double_est_refuse_par_lunicite(calendar_repository, brand_kernel, tmp_path):
    item_id = _produce_draft(calendar_repository, brand_kernel)
    bot = _bot(FakeSession(), calendar_repository, tmp_path)
    bot.notify_pending_drafts()

    session = FakeSession(updates_batches=[
        [_callback(1, item_id, "approve")],
        [_message(2, "/publie https://youtu.be/e2e-doublon")],
    ])
    bot_actif = _bot(session, calendar_repository, tmp_path)
    bot_actif.poll_once()
    bot_actif.poll_once()
    assert calendar_repository.get_item(item_id).status is ContentStatus.PUBLISHED

    # Un second contenu tente d'enregistrer EXACTEMENT le même lien.
    autre_item_id = _produce_draft(calendar_repository, brand_kernel)
    bot_autre = _bot(FakeSession(), calendar_repository, tmp_path)
    bot_autre.notify_pending_drafts()

    session_doublon = FakeSession(updates_batches=[
        [_callback(1, autre_item_id, "approve")],
        [_message(2, "/publie https://youtu.be/e2e-doublon")],
    ])
    bot_doublon = _bot(session_doublon, calendar_repository, tmp_path)
    bot_doublon.poll_once()
    bot_doublon.poll_once()

    # Toujours APPROVED, jamais PUBLISHED : le doublon a été refusé.
    assert calendar_repository.get_item(autre_item_id).status is ContentStatus.APPROVED
    reponse = session_doublon.calls_for("sendMessage")[-1]
    assert "déjà" in reponse["text"].lower()


def test_edit_renvoie_au_redacteur_sans_rien_publier(calendar_repository, brand_kernel, tmp_path):
    item_id = _produce_draft(calendar_repository, brand_kernel)
    bot = _bot(FakeSession(), calendar_repository, tmp_path)
    bot.notify_pending_drafts()

    session = FakeSession(updates_batches=[[_callback(1, item_id, "edit")]])
    bot_edit = _bot(session, calendar_repository, tmp_path)
    bot_edit.poll_once()

    assert calendar_repository.get_item(item_id).status is ContentStatus.DRAFTED
    assert calendar_repository.list_recent_posts() == []

    session_corrige = FakeSession(
        updates_batches=[[_message(2, f"/corrige {item_id} Ton plus direct, moins de blabla.")]]
    )
    bot_corrige = _bot(session_corrige, calendar_repository, tmp_path)
    bot_corrige.poll_once()

    item = calendar_repository.get_item(item_id)
    assert "CORRECTION DEMANDÉE" in (item.body or "")
    assert "Ton plus direct" in (item.body or "")


def test_reject_ferme_le_contenu_sans_rien_publier(calendar_repository, brand_kernel, tmp_path):
    item_id = _produce_draft(calendar_repository, brand_kernel)
    bot = _bot(FakeSession(), calendar_repository, tmp_path)
    bot.notify_pending_drafts()

    session = FakeSession(updates_batches=[[_callback(1, item_id, "reject")]])
    bot_reject = _bot(session, calendar_repository, tmp_path)
    bot_reject.poll_once()

    assert calendar_repository.get_item(item_id).status is ContentStatus.REJECTED
    assert calendar_repository.list_recent_posts() == []


def test_un_chat_id_non_autorise_est_ignore_a_chaque_etape(calendar_repository, brand_kernel, tmp_path):
    item_id = _produce_draft(calendar_repository, brand_kernel)
    bot = _bot(FakeSession(), calendar_repository, tmp_path)
    bot.notify_pending_drafts()

    session = FakeSession(updates_batches=[
        [_callback(1, item_id, "approve", chat_id=_AUTRE_CHAT_ID)],
        [_message(2, "/publie https://youtu.be/intrus", chat_id=_AUTRE_CHAT_ID)],
    ])
    bot_intrus = _bot(session, calendar_repository, tmp_path)
    bot_intrus.poll_once()
    bot_intrus.poll_once()

    # Toujours PENDING_REVIEW : l'intrus n'a rien pu faire.
    assert calendar_repository.get_item(item_id).status is ContentStatus.PENDING_REVIEW
    assert calendar_repository.list_recent_posts() == []
    assert session.calls_for("sendMessage") == []  # aucune réponse envoyée à l'intrus
