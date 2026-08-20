"""Chaîne de fournisseurs LLM avec bascule automatique Gemini → Groq.

Le contrat `LLMPort` est respecté : les agents ne savent pas qu'ils parlent à
une chaîne. Ils appellent `generate()` et obtiennent une réponse, quel que soit
le fournisseur qui a finalement répondu.

Politique de bascule :
- `QuotaExceededError` (429) → on passe **immédiatement** au suivant et on
  marque le fournisseur comme épuisé pour le reste du run ;
- `LLMError` (panne réseau, 5xx) → on passe au suivant sans le marquer épuisé ;
- si tous échouent → `AllProvidersFailedError`.
"""

from __future__ import annotations

import logging

from ...domain.errors import AllProvidersFailedError, LLMError, QuotaExceededError
from ...domain.ports.llm import LLMPort, LLMResponse

logger = logging.getLogger(__name__)


class FallbackLLM(LLMPort):
    """Compose plusieurs `LLMPort` en une chaîne ordonnée."""

    name = "fallback-chain"

    def __init__(self, providers: list[LLMPort]) -> None:
        if not providers:
            raise ValueError("La chaîne LLM doit contenir au moins un fournisseur")
        self.providers = providers
        self._exhausted: set[str] = set()
        #: Statistiques par fournisseur, exposées dans le résumé de run.
        self.usage: dict[str, int] = {p.name: 0 for p in providers}

    def is_available(self) -> bool:
        return any(p.is_available() and p.name not in self._exhausted for p in self.providers)

    def reset(self) -> None:
        """Réarme les fournisseurs marqués épuisés (nouveau run)."""
        self._exhausted.clear()

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        errors: list[str] = []

        for provider in self.providers:
            if provider.name in self._exhausted:
                continue
            if not provider.is_available():
                errors.append(f"{provider.name}: non disponible (clé absente ou quota local épuisé)")
                continue

            try:
                response = provider.generate(
                    system_prompt,
                    user_prompt,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    json_mode=json_mode,
                )
                self.usage[provider.name] = self.usage.get(provider.name, 0) + 1
                return response

            except QuotaExceededError as exc:
                logger.warning("[chaîne LLM] %s a atteint son quota (%s) → bascule", provider.name, exc)
                self._exhausted.add(provider.name)
                errors.append(f"{provider.name}: quota épuisé")

            except LLMError as exc:
                logger.warning("[chaîne LLM] %s en échec (%s) → bascule", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")

        raise AllProvidersFailedError(
            "Tous les fournisseurs LLM ont échoué → " + " | ".join(errors)
        )

    def stats(self) -> str:
        used = ", ".join(f"{name}={count}" for name, count in self.usage.items() if count)
        return used or "aucun appel LLM"
