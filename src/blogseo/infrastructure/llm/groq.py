"""Adapter LLM Groq (free tier) — fournisseur de secours.

API compatible OpenAI, mais appelée en REST brut : on n'installe donc **aucun
SDK OpenAI/Anthropic**, conformément à la contrainte « zéro service payant ».
"""

from __future__ import annotations

import logging
import time

import requests

from ...domain.errors import LLMError, QuotaExceededError
from ...domain.ports.llm import LLMPort, LLMResponse
from ...shared.rate_limiter import RateLimiter
from ...shared.retry import retry

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class GroqLLM(LLMPort):
    """Implémentation `LLMPort` pour Groq free tier (Llama 3.x)."""

    name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        *,
        rate_limiter: RateLimiter | None = None,
        timeout_s: int = 120,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self._limiter = rate_limiter
        self._session = session or requests.Session()

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        # Quota journalier local épuisé : inutile d'appeler, la chaîne basculera.
        return not (self._limiter and self._limiter.remaining_today <= 0)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        if not self.api_key:
            raise LLMError("GROQ_API_KEY absente : impossible d'appeler Groq")

        if self._limiter and not self._limiter.acquire():
            raise QuotaExceededError("Quota journalier Groq épuisé")

        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            # Groq plafonne max_tokens selon le modèle : on reste prudent.
            "max_tokens": min(max_output_tokens, 8_000),
            "top_p": 0.95,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        data = self._post(payload)
        latency = round(time.monotonic() - started, 2)

        choices = data.get("choices") or []
        if not choices:
            raise LLMError("Groq n'a renvoyé aucun choix")
        text = (choices[0].get("message", {}).get("content") or "").strip()
        if not text:
            raise LLMError("Réponse Groq vide")

        usage = data.get("usage", {})
        logger.info("[groq] %s — %s tokens en %.2fs", self.model, usage.get("total_tokens", "?"), latency)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_s=latency,
        )

    @retry(attempts=3, base_delay=2.0, exceptions=(LLMError,), give_up_on=(QuotaExceededError,))
    def _post(self, payload: dict) -> dict:
        try:
            response = self._session.post(
                _ENDPOINT,
                json=payload,
                timeout=self.timeout_s,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        except requests.RequestException as exc:
            raise LLMError(f"Groq injoignable : {exc}") from exc

        if response.status_code == 429:
            raise QuotaExceededError("Groq a renvoyé HTTP 429 (quota free tier atteint)")
        if response.status_code >= 400:
            raise LLMError(f"Groq HTTP {response.status_code} : {response.text[:300]}")

        try:
            return response.json()
        except ValueError as exc:
            raise LLMError(f"Réponse Groq non JSON : {response.text[:200]}") from exc
