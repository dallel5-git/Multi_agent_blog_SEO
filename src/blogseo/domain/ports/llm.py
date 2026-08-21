"""Port `LLMPort` : abstraction du modèle de langage.

Aucune implémentation ne vit dans le domain. Les adapters Cerebras et Groq
(couche infrastructure) implémentent ce contrat, ce qui permet de remplacer le
fournisseur — ou de le simuler dans les tests — sans toucher aux agents.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Réponse normalisée d'un LLM, quel que soit le fournisseur."""

    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMPort(ABC):
    """Contrat minimal attendu par tous les agents."""

    #: Nom lisible du fournisseur ("cerebras", "groq", "fake"...).
    name: str = "llm"

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Génère une complétion. Lève `LLMError`/`QuotaExceededError` en cas d'échec."""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        max_output_tokens: int = 4096,
    ) -> dict:
        """Génère une réponse JSON. Implémentation par défaut = generate + parsing tolérant."""
        from ...shared.json_utils import extract_json  # import tardif : évite un cycle

        response = self.generate(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            json_mode=True,
        )
        return extract_json(response.text)

    def is_available(self) -> bool:
        """Indique si le fournisseur est utilisable (clé présente, quota non épuisé)."""
        return True
