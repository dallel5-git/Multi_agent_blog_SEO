"""Adapter LLM OpenRouter (modèles `:free`) — filet de secours supplémentaire.

API compatible OpenAI, appelée en REST brut, même patron que `GroqLLM` et
`CerebrasLLM`. OpenRouter agrège plusieurs modèles gratuits (suffixe `:free`,
0 $ garanti) derrière une seule clé — utile comme secours quand Cerebras ou
Gemini sont indisponibles (quota, facturation, projet bloqué...).
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

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterLLM(LLMPort):
    """Implémentation `LLMPort` pour OpenRouter (modèles gratuits `:free`).

    `name` est réglable par instance (et non figé sur la classe) : la chaîne
    peut ainsi enchaîner deux modèles OpenRouter différents sous la même clé
    (ex. "openrouter", "openrouter-2") sans que `FallbackLLM` les confonde —
    son suivi de quota épuisé (`_exhausted`) et ses statistiques d'usage sont
    indexés par `name`.
    """

    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "nvidia/nemotron-3-super-120b-a12b:free",
        *,
        name: str | None = None,
        rate_limiter: RateLimiter | None = None,
        timeout_s: int = 120,
        session: requests.Session | None = None,
    ) -> None:
        if name:
            self.name = name
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self._limiter = rate_limiter
        self._session = session or requests.Session()

    def is_available(self) -> bool:
        if not self.api_key:
            return False
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
            raise LLMError("OPENROUTER_API_KEY absente : impossible d'appeler OpenRouter")

        if self._limiter and not self._limiter.acquire():
            raise QuotaExceededError("Quota journalier OpenRouter épuisé")

        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "top_p": 0.95,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        data = self._post(payload)
        latency = round(time.monotonic() - started, 2)

        choices = data.get("choices") or []
        if not choices:
            raise LLMError("OpenRouter n'a renvoyé aucun choix")
        text = (choices[0].get("message", {}).get("content") or "").strip()
        if not text:
            raise LLMError("Réponse OpenRouter vide")

        usage = data.get("usage", {})
        logger.info(
            "[openrouter] %s — %s tokens en %.2fs", self.model, usage.get("total_tokens", "?"), latency
        )
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
                    # Recommandés par OpenRouter (attribution, sans effet sur l'auth).
                    "HTTP-Referer": "https://github.com/dallel5-git/Multi_agent_blog_SEO",
                    "X-Title": "blogseo-agents",
                },
            )
        except requests.RequestException as exc:
            raise LLMError(f"OpenRouter injoignable : {exc}") from exc

        if response.status_code == 429:
            raise QuotaExceededError("OpenRouter a renvoyé HTTP 429 (quota free tier atteint)")
        if response.status_code >= 400:
            raise LLMError(f"OpenRouter HTTP {response.status_code} : {response.text[:300]}")

        try:
            return response.json()
        except ValueError as exc:
            raise LLMError(f"Réponse OpenRouter non JSON : {response.text[:200]}") from exc
