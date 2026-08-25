"""Tests du socle commun des bots de pilotage (`pilotage.bots.base`, issue #64).

Mêmes principes de mock que `tests/unit/test_telegram_bot.py` (le bot de
validation du blog) : une `FakeSession` encaisse les appels HTTP et sert des
lots d'`updates` prédéfinis — jamais de vrai réseau dans ces tests.
"""

from __future__ import annotations

from pilotage.bots.base import BotConfig, PilotageBot, create_bot_for_platform
from pilotage.platforms import Platform
from pilotage.shared_calendar.models import ContentItem, ContentStatus, PlatformPost


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Simule `requests.Session` : encaisse les appels, sert des lots d'updates."""

    def __init__(self, updates_batches: list[list[dict]] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._updates_batches = list(updates_batches or [])

    def post(self, url, *, json=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        payload = json or {}
        self.calls.append((method, payload))
        if method == "getUpdates":
            batch = self._updates_batches.pop(0) if self._updates_batches else []
            return FakeResponse({"ok": True, "result": batch})
        return FakeResponse({"ok": True, "result": {}})

    def calls_for(self, method: str) -> list[dict]:
        return [payload for name, payload in self.calls if name == method]


_CHAT_ID = "12345"
_AUTRE_CHAT_ID = "99999"


def make_bot(
    session: FakeSession,
    calendar_repository,
    *,
    platform: Platform = Platform.YOUTUBE,
    offset_path=None,
    tmp_path=None,
) -> PilotageBot:
    chemin = offset_path or (tmp_path / "offset.json" if tmp_path else None)
    config = BotConfig(platform=platform, token="fake-token", chat_id=_CHAT_ID, offset_path=chemin, timeout_s=5)
    return PilotageBot(config, calendar_repository, session=session)


def message_update(update_id: int, text: str, *, chat_id: str = _CHAT_ID) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


def callback_update(update_id: int, item_id: int, action: str, *, chat_id: str = _CHAT_ID) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cbq{update_id}",
            "data": f"pilotage:{item_id}:{action}",
            "message": {"chat": {"id": chat_id}, "message_id": 1},
        },
    }


# --------------------------------------------------------------------------- #
# create_bot_for_platform
# --------------------------------------------------------------------------- #
def test_create_bot_for_platform_construit_un_bot_configure(calendar_repository, tmp_path):
    bot = create_bot_for_platform(
        Platform.YOUTUBE, token="t", chat_id="1", offset_path=tmp_path / "o.json",
        repository=calendar_repository,
    )
    assert bot.is_configured() is True


def test_bot_sans_token_nest_pas_configure(calendar_repository, tmp_path):
    bot = create_bot_for_platform(
        Platform.YOUTUBE, token="", chat_id="", offset_path=tmp_path / "o.json",
        repository=calendar_repository,
    )
    assert bot.is_configured() is False


def test_run_forever_sarrete_immediatement_si_non_configure(calendar_repository, tmp_path, caplog):
    bot = create_bot_for_platform(
        Platform.YOUTUBE, token="", chat_id="", offset_path=tmp_path / "o.json",
        repository=calendar_repository,
    )
    bot.run_forever()  # ne doit jamais boucler ni lever


# --------------------------------------------------------------------------- #
# Garde chat_id
# --------------------------------------------------------------------------- #
def test_un_message_dun_autre_chat_id_est_ignore(calendar_repository, tmp_path):
    session = FakeSession(updates_batches=[[message_update(1, "/en_attente", chat_id=_AUTRE_CHAT_ID)]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert session.calls_for("sendMessage") == []


def test_un_callback_dun_autre_chat_id_est_ignore(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    calendar_repository.update_status(item_id, ContentStatus.PENDING_REVIEW)
    session = FakeSession(updates_batches=[[callback_update(1, item_id, "approve", chat_id=_AUTRE_CHAT_ID)]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    item = calendar_repository.get_item(item_id)
    assert item.status is ContentStatus.PENDING_REVIEW  # inchangé


# --------------------------------------------------------------------------- #
# Offset — jamais rejoué au redémarrage
# --------------------------------------------------------------------------- #
def test_offset_absent_vaut_zero(calendar_repository, tmp_path):
    bot = make_bot(FakeSession(), calendar_repository, tmp_path=tmp_path)
    assert bot._load_offset() == 0


def test_offset_avance_apres_un_tour_de_sondage(calendar_repository, tmp_path):
    session = FakeSession(updates_batches=[[message_update(7, "/stats")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert bot._load_offset() == 8  # update_id (7) + 1


def test_une_nouvelle_instance_relit_loffset_persiste(calendar_repository, tmp_path):
    offset_path = tmp_path / "offset.json"
    session1 = FakeSession(updates_batches=[[message_update(3, "/stats")]])
    make_bot(session1, calendar_repository, offset_path=offset_path).poll_once()

    session2 = FakeSession(updates_batches=[])
    bot2 = make_bot(session2, calendar_repository, offset_path=offset_path)

    assert bot2._load_offset() == 4
    bot2.poll_once()
    assert session2.calls_for("getUpdates")[0]["offset"] == 4  # jamais rejoué


# --------------------------------------------------------------------------- #
# /en_attente
# --------------------------------------------------------------------------- #
def test_en_attente_liste_les_contenus_avec_un_clavier_a_trois_boutons(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="Mon sujet"))
    calendar_repository.update_status(item_id, ContentStatus.PENDING_REVIEW)
    session = FakeSession(updates_batches=[[message_update(1, "/en_attente")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    send = session.calls_for("sendMessage")[0]
    assert "Mon sujet" in send["text"]
    boutons = send["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in boutons] == [
        f"pilotage:{item_id}:approve", f"pilotage:{item_id}:edit", f"pilotage:{item_id}:reject",
    ]


def test_en_attente_ne_voit_que_sa_propre_plateforme(calendar_repository, tmp_path):
    yt_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="YouTube"))
    calendar_repository.update_status(yt_id, ContentStatus.PENDING_REVIEW)
    tk_id = calendar_repository.add_item(ContentItem(platform=Platform.TIKTOK, title="TikTok"))
    calendar_repository.update_status(tk_id, ContentStatus.PENDING_REVIEW)

    session = FakeSession(updates_batches=[[message_update(1, "/en_attente")]])
    bot = make_bot(session, calendar_repository, platform=Platform.YOUTUBE, tmp_path=tmp_path)
    bot.poll_once()

    textes = " ".join(call["text"] for call in session.calls_for("sendMessage"))
    assert "YouTube" in textes
    assert "TikTok" not in textes


def test_en_attente_vide_previent_plutot_que_de_ne_rien_dire(calendar_repository, tmp_path):
    session = FakeSession(updates_batches=[[message_update(1, "/en_attente")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert "Rien en attente" in session.calls_for("sendMessage")[0]["text"]


# --------------------------------------------------------------------------- #
# Boutons ✅ ✏️ ❌
# --------------------------------------------------------------------------- #
def test_bouton_approve_passe_le_statut_a_approved_et_retire_le_clavier(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    calendar_repository.update_status(item_id, ContentStatus.PENDING_REVIEW)
    session = FakeSession(updates_batches=[[callback_update(1, item_id, "approve")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert calendar_repository.get_item(item_id).status is ContentStatus.APPROVED
    assert session.calls_for("editMessageReplyMarkup")[0]["reply_markup"]["inline_keyboard"] == []
    assert session.calls_for("answerCallbackQuery")


def test_bouton_reject_passe_le_statut_a_rejected(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    session = FakeSession(updates_batches=[[callback_update(1, item_id, "reject")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert calendar_repository.get_item(item_id).status is ContentStatus.REJECTED


def test_bouton_edit_renvoie_a_drafted_sans_rien_publier(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    calendar_repository.update_status(item_id, ContentStatus.PENDING_REVIEW)
    session = FakeSession(updates_batches=[[callback_update(1, item_id, "edit")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert calendar_repository.get_item(item_id).status is ContentStatus.DRAFTED
    assert calendar_repository.list_recent_posts() == []  # rien publié


def test_bouton_sur_un_contenu_dune_autre_plateforme_est_refuse(calendar_repository, tmp_path):
    """Le bot YouTube ne doit jamais agir sur un contenu TikTok."""
    tk_id = calendar_repository.add_item(ContentItem(platform=Platform.TIKTOK, title="T"))
    session = FakeSession(updates_batches=[[callback_update(1, tk_id, "approve")]])
    bot = make_bot(session, calendar_repository, platform=Platform.YOUTUBE, tmp_path=tmp_path)

    bot.poll_once()

    assert calendar_repository.get_item(tk_id).status is ContentStatus.IDEA  # inchangé


# --------------------------------------------------------------------------- #
# /publie
# --------------------------------------------------------------------------- #
def test_publie_avec_un_seul_argument_prend_le_plus_ancien_approuve(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    calendar_repository.update_status(item_id, ContentStatus.APPROVED)
    session = FakeSession(updates_batches=[[message_update(1, "/publie https://youtu.be/abc")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert calendar_repository.get_item(item_id).status is ContentStatus.PUBLISHED
    posts = calendar_repository.list_recent_posts()
    assert posts[0].url == "https://youtu.be/abc"


def test_publie_avec_id_explicite(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    calendar_repository.update_status(item_id, ContentStatus.APPROVED)
    session = FakeSession(updates_batches=[[message_update(1, f"/publie {item_id} https://youtu.be/xyz")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert calendar_repository.find_post_by_url("https://youtu.be/xyz") is not None


def test_publie_refuse_un_lien_deja_enregistre(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="T"))
    calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.YOUTUBE,
                     url="https://youtu.be/doublon", published_at="2026-08-25")
    )
    autre_item_id = calendar_repository.add_item(ContentItem(platform=Platform.YOUTUBE, title="Autre"))
    calendar_repository.update_status(autre_item_id, ContentStatus.APPROVED)

    session = FakeSession(updates_batches=[
        [message_update(1, f"/publie {autre_item_id} https://youtu.be/doublon")]
    ])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert "déjà enregistré" in session.calls_for("sendMessage")[0]["text"]
    assert calendar_repository.get_item(autre_item_id).status is ContentStatus.APPROVED  # inchangé


def test_publie_sans_contenu_approuve_previent(calendar_repository, tmp_path):
    session = FakeSession(updates_batches=[[message_update(1, "/publie https://youtu.be/abc")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    assert "Aucun contenu approuvé" in session.calls_for("sendMessage")[0]["text"]


# --------------------------------------------------------------------------- #
# /corrige
# --------------------------------------------------------------------------- #
def test_corrige_prefixe_le_brouillon_avec_le_retour(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(
        ContentItem(platform=Platform.YOUTUBE, title="T", body="Script original.")
    )
    session = FakeSession(updates_batches=[[message_update(1, f"/corrige {item_id} trop long, raccourcis")]])
    bot = make_bot(session, calendar_repository, tmp_path=tmp_path)

    bot.poll_once()

    item = calendar_repository.get_item(item_id)
    assert "trop long, raccourcis" in item.body
    assert "Script original." in item.body


# --------------------------------------------------------------------------- #
# Rappel hebdomadaire de saisie manuelle
# --------------------------------------------------------------------------- #
def test_compose_manual_stats_reminder_liste_les_posts_sans_mesure(calendar_repository, tmp_path):
    item_id = calendar_repository.add_item(ContentItem(platform=Platform.TIKTOK, title="T"))
    calendar_repository.add_post(
        PlatformPost(content_item_id=item_id, platform=Platform.TIKTOK,
                     url="https://tiktok.com/@x/1", published_at="2026-08-25")
    )
    bot = make_bot(FakeSession(), calendar_repository, platform=Platform.TIKTOK, tmp_path=tmp_path)

    message = bot.compose_manual_stats_reminder()

    assert message is not None
    assert "tiktok.com/@x/1" in message


def test_compose_manual_stats_reminder_renvoie_none_sans_publication_a_relancer(
    calendar_repository, tmp_path
):
    bot = make_bot(FakeSession(), calendar_repository, platform=Platform.TIKTOK, tmp_path=tmp_path)
    assert bot.compose_manual_stats_reminder() is None
