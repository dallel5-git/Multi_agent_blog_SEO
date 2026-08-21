"""Tests de `CerebrasLLM` — nouveau fournisseur principal (remplace Gemini, ADR 0006).

Le vrai réseau est simulé par `FakeSession` (même approche que pour
`TelegramBot`/`SearchConsoleAnalytics`) : aucune clé Cerebras réelle n'était
disponible au moment de l'écriture, donc ce test verrouille le contrat REST
attendu (payload envoyé, extraction de la réponse, mapping des erreurs HTTP)
plutôt que de valider un appel réel.
"""

from __future__ import annotations

import pytest

from blogseo.domain.errors import LLMError, QuotaExceededError
from blogseo.infrastructure.llm.cerebras import CerebrasLLM


class FakeResponse:
    def __init__(self, payload: dict | None = None, status_code: int = 200, text: str = "") -> None:
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []

    def post(self, url, *, json=None, timeout=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def chat_response(content: str, **usage) -> FakeResponse:
    return FakeResponse({
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, **usage},
    })


class TestDisponibilite:
    def test_indisponible_sans_cle(self):
        assert CerebrasLLM("", session=FakeSession(chat_response("x"))).is_available() is False

    def test_disponible_avec_cle(self):
        assert CerebrasLLM("key", session=FakeSession(chat_response("x"))).is_available() is True


class TestGenerate:
    def test_leve_une_erreur_sans_cle(self):
        with pytest.raises(LLMError):
            CerebrasLLM("", session=FakeSession(chat_response("x"))).generate("s", "u")

    def test_construit_le_payload_attendu(self):
        session = FakeSession(chat_response("réponse"))
        CerebrasLLM("key", "llama-3.3-70b", session=session).generate(
            "système", "utilisateur", temperature=0.5, max_output_tokens=500, json_mode=True,
        )
        call = session.calls[0]
        assert call["url"] == "https://api.cerebras.ai/v1/chat/completions"
        assert call["headers"]["Authorization"] == "Bearer key"
        assert call["json"]["model"] == "llama-3.3-70b"
        assert call["json"]["messages"] == [
            {"role": "system", "content": "système"},
            {"role": "user", "content": "utilisateur"},
        ]
        assert call["json"]["temperature"] == 0.5
        assert call["json"]["max_tokens"] == 500
        assert call["json"]["response_format"] == {"type": "json_object"}

    def test_json_mode_desactive_par_defaut(self):
        session = FakeSession(chat_response("réponse"))
        CerebrasLLM("key", session=session).generate("s", "u")
        assert "response_format" not in session.calls[0]["json"]

    def test_extrait_le_texte_et_les_tokens(self):
        session = FakeSession(chat_response("voici la réponse"))
        resp = CerebrasLLM("key", session=session).generate("s", "u")
        assert resp.text == "voici la réponse"
        assert resp.provider == "cerebras"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5

    def test_429_leve_quota_exceeded(self):
        session = FakeSession(FakeResponse(status_code=429, text="rate limited"))
        with pytest.raises(QuotaExceededError):
            CerebrasLLM("key", session=session).generate("s", "u")

    def test_erreur_http_leve_llm_error(self):
        session = FakeSession(FakeResponse(status_code=500, text="server error"))
        with pytest.raises(LLMError):
            CerebrasLLM("key", session=session).generate("s", "u")

    def test_reponse_sans_choix_leve_llm_error(self):
        session = FakeSession(FakeResponse({"choices": []}))
        with pytest.raises(LLMError):
            CerebrasLLM("key", session=session).generate("s", "u")

    def test_contenu_vide_leve_llm_error(self):
        session = FakeSession(chat_response(""))
        with pytest.raises(LLMError):
            CerebrasLLM("key", session=session).generate("s", "u")

    def test_panne_reseau_leve_llm_error(self):
        import requests

        session = FakeSession(requests.ConnectionError("DNS injoignable"))
        with pytest.raises(LLMError):
            CerebrasLLM("key", session=session).generate("s", "u")
