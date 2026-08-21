"""Adapter LLM Google Gemini (free tier).

Non câblé par défaut dans `Container.llm` (remplacé par `CerebrasLLM` comme
fournisseur principal — voir ADR 0003). Classe conservée telle quelle : pour
la réutiliser, il suffit de l'ajouter à la liste `providers` de
`Container.llm` (`infrastructure/config/container.py`).

Appel direct à l'API REST `generativelanguage.googleapis.com` via `requests` :
pas de SDK lourd, pas de dépendance qui change d'API tous les deux mois, et un
contrôle total sur la détection du 429 (quota) nécessaire au fallback.
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

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiLLM(LLMPort):
    """Implémentation `LLMPort` pour Gemini free tier."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.6-flash",
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

    # ------------------------------------------------------------------ #
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
            raise LLMError("GEMINI_API_KEY absente : impossible d'appeler Gemini")

        # Le rate limiter bloque AVANT l'appel pour ne pas brûler le quota en 429.
        if self._limiter and not self._limiter.acquire():
            raise QuotaExceededError("Quota journalier Gemini épuisé")

        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "topP": 0.95,
            },
            # Le sujet « IA & sécurité » déclenche parfois les filtres : on les desserre
            # au minimum autorisé par le free tier pour éviter les réponses vides.
            "safetySettings": [
                {"category": c, "threshold": "BLOCK_ONLY_HIGH"}
                for c in (
                    "HARM_CATEGORY_HARASSMENT",
                    "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "HARM_CATEGORY_DANGEROUS_CONTENT",
                )
            ],
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        started = time.monotonic()
        data = self._post(payload)
        latency = round(time.monotonic() - started, 2)

        text = self._extract_text(data)
        usage = data.get("usageMetadata", {})
        logger.info(
            "[gemini] %s — %s tokens en %.2fs", self.model,
            usage.get("totalTokenCount", "?"), latency,
        )
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
            latency_s=latency,
        )

    @retry(attempts=3, base_delay=2.0, exceptions=(LLMError,), give_up_on=(QuotaExceededError,))
    def _post(self, payload: dict) -> dict:
        url = f"{_BASE_URL}/{self.model}:generateContent"
        try:
            response = self._session.post(
                url,
                params={"key": self.api_key},
                json=payload,
                timeout=self.timeout_s,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            raise LLMError(f"Gemini injoignable : {exc}") from exc

        if response.status_code == 429:
            raise QuotaExceededError("Gemini a renvoyé HTTP 429 (quota free tier atteint)")
        if response.status_code >= 400:
            raise LLMError(f"Gemini HTTP {response.status_code} : {response.text[:300]}")

        try:
            return response.json()
        except ValueError as exc:
            raise LLMError(f"Réponse Gemini non JSON : {response.text[:200]}") from exc

    @staticmethod
    def _extract_text(data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            reason = data.get("promptFeedback", {}).get("blockReason", "inconnue")
            raise LLMError(f"Gemini n'a renvoyé aucun candidat (raison : {reason})")

        candidate = candidates[0]
        parts = candidate.get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            raise LLMError(
                f"Réponse Gemini vide (finishReason : {candidate.get('finishReason', 'inconnu')})"
            )
        return text
