"""Tests de `OpenRouterLLM` — 2e maillon de la chaîne LLM (ADR 0007).

Même approche que `test_cerebras_llm.py` : aucune clé OpenRouter réelle
disponible au moment de l'écriture, le contrat REST est donc verrouillé via
une session HTTP simulée plutôt que validé par un appel réel.
"""

from __future__ import annotations

import pytest

from blogseo.domain.errors import LLMError, QuotaExceededError
from blogseo.infrastructure.llm.openrouter import OpenRouterLLM


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


def chat_response(content: str) -> FakeResponse:
    return FakeResponse({
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })


class TestDisponibilite:
    def test_indisponible_sans_cle(self):
        assert OpenRouterLLM("", session=FakeSession(chat_response("x"))).is_available() is False

    def test_disponible_avec_cle(self):
        assert OpenRouterLLM("key", session=FakeSession(chat_response("x"))).is_available() is True


class TestGenerate:
    def test_leve_une_erreur_sans_cle(self):
        with pytest.raises(LLMError):
            OpenRouterLLM("", session=FakeSession(chat_response("x"))).generate("s", "u")

    def test_construit_le_payload_attendu(self):
        session = FakeSession(chat_response("réponse"))
        OpenRouterLLM("key", "meta-llama/llama-3.3-70b-instruct:free", session=session).generate(
            "système", "utilisateur", temperature=0.5, max_output_tokens=500, json_mode=True,
        )
        call = session.calls[0]
        assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
        assert call["headers"]["Authorization"] == "Bearer key"
        assert call["json"]["model"] == "meta-llama/llama-3.3-70b-instruct:free"
        assert call["json"]["messages"] == [
            {"role": "system", "content": "système"},
            {"role": "user", "content": "utilisateur"},
        ]
        assert call["json"]["response_format"] == {"type": "json_object"}

    def test_json_mode_desactive_par_defaut(self):
        session = FakeSession(chat_response("réponse"))
        OpenRouterLLM("key", session=session).generate("s", "u")
        assert "response_format" not in session.calls[0]["json"]

    def test_extrait_le_texte_et_les_tokens(self):
        session = FakeSession(chat_response("voici la réponse"))
        resp = OpenRouterLLM("key", session=session).generate("s", "u")
        assert resp.text == "voici la réponse"
        assert resp.provider == "openrouter"
        assert resp.prompt_tokens == 10

    def test_429_leve_quota_exceeded(self):
        session = FakeSession(FakeResponse(status_code=429, text="rate limited"))
        with pytest.raises(QuotaExceededError):
            OpenRouterLLM("key", session=session).generate("s", "u")

    def test_erreur_http_leve_llm_error(self):
        session = FakeSession(FakeResponse(status_code=402, text="payment required"))
        with pytest.raises(LLMError):
            OpenRouterLLM("key", session=session).generate("s", "u")

    def test_contenu_vide_leve_llm_error(self):
        session = FakeSession(chat_response(""))
        with pytest.raises(LLMError):
            OpenRouterLLM("key", session=session).generate("s", "u")

    def test_panne_reseau_leve_llm_error(self):
        import requests

        session = FakeSession(requests.ConnectionError("DNS injoignable"))
        with pytest.raises(LLMError):
            OpenRouterLLM("key", session=session).generate("s", "u")
