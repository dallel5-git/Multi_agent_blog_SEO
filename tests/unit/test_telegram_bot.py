"""Tests de `TelegramBot` : clavier à trois boutons, anti double-décision,
persistance de l'offset `getUpdates`, et repli `NullNotifier`.

Fait partie d'EPIC 5 (issue #27) : la règle métier centrale (✅ publie+push,
❌ écrit seulement, 🔁 ne touche pas au blog) dépend de la fiabilité de ce
canal — un vieux callback rejoué ou un double clic ne doit jamais changer
la décision.
"""

from __future__ import annotations

from blogseo.domain.entities.pipeline_run import Decision
from blogseo.infrastructure.notifications.telegram import NullNotifier, TelegramBot


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

    def post(self, url, *, json=None, data=None, files=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        payload = json if json is not None else (data or {})
        self.calls.append((method, payload))
        if method == "getUpdates":
            batch = self._updates_batches.pop(0) if self._updates_batches else []
            return FakeResponse({"ok": True, "result": batch})
        return FakeResponse({"ok": True, "result": {}})

    def calls_for(self, method: str) -> list[dict]:
        return [payload for name, payload in self.calls if name == method]


def make_bot(session: FakeSession, *, state_dir=None) -> TelegramBot:
    return TelegramBot("fake-token", "12345", state_dir=state_dir, session=session, timeout_s=5)


def callback_update(update_id: int, run_id: str, decision_value: str, *, message_id: int = 1) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cbq{update_id}",
            "data": f"blogseo:{run_id}:{decision_value}",
            "message": {"chat": {"id": 12345}, "message_id": message_id},
        },
    }


class TestDecisionDepuisUpdate:
    def test_callback_valide_pour_le_bon_run(self):
        bot = make_bot(FakeSession())
        update = callback_update(1, "run-abc", Decision.APPROVE.value)

        assert bot._decision_from_update(update, "run-abc") == Decision.APPROVE

    def test_callback_pour_un_autre_run_est_ignore(self):
        bot = make_bot(FakeSession())
        update = callback_update(1, "run-autre", Decision.APPROVE.value)

        assert bot._decision_from_update(update, "run-abc") is None

    def test_update_sans_callback_query_est_ignore(self):
        bot = make_bot(FakeSession())

        assert bot._decision_from_update({"update_id": 1, "message": {}}, "run-abc") is None

    def test_valeur_de_decision_inconnue_est_ignoree(self):
        bot = make_bot(FakeSession())
        update = callback_update(1, "run-abc", "annuler")

        assert bot._decision_from_update(update, "run-abc") is None


class TestOffsetPersiste:
    def test_offset_absent_vaut_zero(self, tmp_path):
        bot = make_bot(FakeSession(), state_dir=tmp_path)
        assert bot._load_offset() == 0

    def test_offset_sauvegarde_puis_relu_par_une_nouvelle_instance(self, tmp_path):
        make_bot(FakeSession(), state_dir=tmp_path)._save_offset(42)

        bot2 = make_bot(FakeSession(), state_dir=tmp_path)
        assert bot2._load_offset() == 42

    def test_fichier_d_offset_corrompu_retombe_a_zero(self, tmp_path):
        (tmp_path / "telegram_offset.json").write_text("{pas du json valide", encoding="utf-8")
        bot = make_bot(FakeSession(), state_dir=tmp_path)
        assert bot._load_offset() == 0

    def test_sans_state_dir_l_offset_n_est_jamais_ecrit(self):
        bot = make_bot(FakeSession(), state_dir=None)
        bot._save_offset(7)  # ne doit pas lever
        assert bot._load_offset() == 0


class TestRequestDecision:
    def test_envoie_un_clavier_a_trois_boutons(self):
        session = FakeSession(updates_batches=[[callback_update(1, "run-1", Decision.REJECT.value)]])
        bot = make_bot(session)

        bot.request_decision(run_id="run-1", title="Titre", preview="Aperçu")

        send = session.calls_for("sendMessage")[0]
        buttons = [b for row in send["reply_markup"]["inline_keyboard"] for b in row]
        assert len(buttons) == 3
        callback_data = {b["callback_data"] for b in buttons}
        assert callback_data == {
            f"blogseo:run-1:{Decision.APPROVE.value}",
            f"blogseo:run-1:{Decision.REJECT.value}",
            f"blogseo:run-1:{Decision.REWRITE.value}",
        }

    def test_decision_recue_retire_le_clavier_et_confirme(self):
        session = FakeSession(updates_batches=[[callback_update(1, "run-1", Decision.APPROVE.value)]])
        bot = make_bot(session)

        decision = bot.request_decision(run_id="run-1", title="Titre", preview="Aperçu")

        assert decision == Decision.APPROVE
        assert session.calls_for("answerCallbackQuery")
        edit = session.calls_for("editMessageReplyMarkup")[0]
        assert edit["reply_markup"]["inline_keyboard"] == []

    def test_offset_avance_et_ignore_un_callback_d_un_autre_run(self, tmp_path):
        session = FakeSession(updates_batches=[
            [callback_update(1, "run-autre", Decision.APPROVE.value)],
            [callback_update(2, "run-1", Decision.REJECT.value)],
        ])
        bot = make_bot(session, state_dir=tmp_path)

        decision = bot.request_decision(run_id="run-1", title="Titre", preview="Aperçu")

        assert decision == Decision.REJECT
        assert bot._load_offset() == 3  # dernier update_id (2) + 1, jamais rejoué

    def test_aucune_decision_dans_le_delai_renvoie_none(self):
        bot = make_bot(FakeSession(updates_batches=[]), )
        bot.timeout_s = 5

        decision = bot.request_decision(run_id="run-1", title="Titre", preview="Aperçu", timeout_s=1)

        assert decision is None


class TestAcknowledge:
    def test_envoie_un_message_recap(self):
        session = FakeSession()
        bot = make_bot(session)

        bot.acknowledge("run-1", Decision.APPROVE, "Publié avec succès")

        send = session.calls_for("sendMessage")[0]
        assert "run-1" in send["text"]
        assert "Publié avec succès" in send["text"]


class TestNullNotifier:
    def test_decision_par_defaut_est_reject(self):
        notifier = NullNotifier()
        decision = notifier.request_decision(run_id="run-1", title="Titre", preview="Aperçu")
        assert decision == Decision.REJECT

    def test_decision_par_defaut_est_configurable(self):
        notifier = NullNotifier(default_decision=Decision.APPROVE)
        decision = notifier.request_decision(run_id="run-1", title="Titre", preview="Aperçu")
        assert decision == Decision.APPROVE

    def test_n_est_jamais_disponible(self):
        assert NullNotifier().is_available() is False
