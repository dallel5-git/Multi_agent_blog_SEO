"""Appel LLM minimal pour les rédacteurs du pilotage.

Volontairement plus modeste que `blogseo.infrastructure.llm` (chaîne à quatre
fournisseurs, rate limiting, retries) — ce n'est pas dupliqué ici, la règle
d'isolation interdisant l'import. Un seul fournisseur réel (Groq, appelé en
REST brut, sans SDK) plus un fournisseur factice pour le mode hors ligne :
suffisant pour un pipeline de pilotage, qui produit un brouillon par run et
non un article relu par cinq agents.

`resolve_llm()` choisit le factice dès que `offline=True` ou qu'aucune clé
n'est configurée : un pipeline ne doit jamais exiger de clé pour tourner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import requests

_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str


class LLMPort(Protocol):
    def generate(
        self, system_prompt: str, user_prompt: str, *, temperature: float = 0.7, json_mode: bool = False
    ) -> LLMResponse: ...


@dataclass(slots=True)
class FakeLLM:
    """Réponses plausibles et déterministes, sans réseau — mode hors ligne."""

    name: str = "fake"
    calls: list[tuple[str, str]] = field(default_factory=list)

    def generate(
        self, system_prompt: str, user_prompt: str, *, temperature: float = 0.7, json_mode: bool = False
    ) -> LLMResponse:
        self.calls.append((system_prompt[:80], user_prompt[:80]))
        if json_mode:
            text = '{"title": "Sujet généré hors ligne", "angle": "Angle générique, LLM factice."}'
        else:
            text = (
                "Contenu généré par le LLM factice (mode hors ligne) — texte plausible mais "
                "non destiné à la publication. Utilisez une vraie clé API (GROQ_API_KEY) pour "
                "un brouillon exploitable."
            )
        return LLMResponse(text=text, provider=self.name, model="fake-1")


class GroqLLM:
    """Appel REST brut à Groq (API compatible OpenAI, aucun SDK installé)."""

    name = "groq"

    def __init__(self, api_key: str, model: str = _GROQ_DEFAULT_MODEL, *, timeout_s: int = 60) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def generate(
        self, system_prompt: str, user_prompt: str, *, temperature: float = 0.7, json_mode: bool = False
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                _GROQ_ENDPOINT,
                json=payload,
                timeout=self.timeout_s,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Groq injoignable : {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(f"Groq HTTP {response.status_code} : {response.text[:300]}")

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Groq n'a renvoyé aucun choix")
        text = (choices[0].get("message", {}).get("content") or "").strip()
        if not text:
            raise RuntimeError("Réponse Groq vide")

        return LLMResponse(text=text, provider=self.name, model=self.model)


def resolve_llm(*, offline: bool, api_key: str = "") -> LLMPort:
    """Factice si `offline` ou si aucune clé n'est configurée, Groq sinon."""
    if offline or not api_key:
        return FakeLLM()
    return GroqLLM(api_key)
