"""Tests de la chaîne LLM (bascule Cerebras → Groq) et du rate limiter."""

from __future__ import annotations

import pytest

from blogseo.domain.errors import AllProvidersFailedError, LLMError, QuotaExceededError
from blogseo.domain.ports.llm import LLMPort, LLMResponse
from blogseo.infrastructure.llm.fallback_chain import FallbackLLM
from blogseo.shared.rate_limiter import RateLimitConfig, RateLimiter


class StubLLM(LLMPort):
    def __init__(self, name: str, *, error: Exception | None = None, available: bool = True) -> None:
        self.name = name
        self.error = error
        self.available = available
        self.calls = 0

    def is_available(self) -> bool:
        return self.available

    def generate(self, system_prompt, user_prompt, **kwargs) -> LLMResponse:
        self.calls += 1
        if self.error:
            raise self.error
        return LLMResponse(text=f"réponse de {self.name}", provider=self.name, model="stub")


class TestChaineDeFallback:
    def test_utilise_le_premier_fournisseur_disponible(self):
        primaire, secours = StubLLM("cerebras"), StubLLM("groq")
        chain = FallbackLLM([primaire, secours])
        assert chain.generate("s", "u").provider == "cerebras"
        assert secours.calls == 0

    def test_bascule_sur_quota_429(self):
        primaire = StubLLM("cerebras", error=QuotaExceededError("429"))
        secours = StubLLM("groq")
        chain = FallbackLLM([primaire, secours])
        assert chain.generate("s", "u").provider == "groq"

    def test_un_fournisseur_en_quota_est_ecarte_pour_la_suite_du_run(self):
        primaire = StubLLM("cerebras", error=QuotaExceededError("429"))
        secours = StubLLM("groq")
        chain = FallbackLLM([primaire, secours])
        chain.generate("s", "u")
        chain.generate("s", "u")
        # Le fournisseur épuisé n'est plus rappelé du tout.
        assert primaire.calls == 1
        assert secours.calls == 2

    def test_bascule_sur_erreur_reseau_sans_ecarter_definitivement(self):
        primaire = StubLLM("cerebras", error=LLMError("timeout"))
        secours = StubLLM("groq")
        chain = FallbackLLM([primaire, secours])
        chain.generate("s", "u")
        chain.generate("s", "u")
        assert primaire.calls == 2  # on retente au coup suivant

    def test_ignore_un_fournisseur_indisponible(self):
        primaire = StubLLM("cerebras", available=False)
        secours = StubLLM("groq")
        assert FallbackLLM([primaire, secours]).generate("s", "u").provider == "groq"
        assert primaire.calls == 0

    def test_leve_si_tout_echoue(self):
        chain = FallbackLLM([
            StubLLM("cerebras", error=QuotaExceededError("429")),
            StubLLM("groq", error=LLMError("500")),
        ])
        with pytest.raises(AllProvidersFailedError) as exc:
            chain.generate("s", "u")
        assert "cerebras" in str(exc.value) and "groq" in str(exc.value)

    def test_reset_rearme_les_fournisseurs(self):
        primaire = StubLLM("cerebras", error=QuotaExceededError("429"))
        chain = FallbackLLM([primaire, StubLLM("groq")])
        chain.generate("s", "u")
        chain.reset()
        chain.generate("s", "u")
        assert primaire.calls == 2

    def test_comptabilise_les_appels(self):
        chain = FallbackLLM([StubLLM("cerebras")])
        chain.generate("s", "u")
        chain.generate("s", "u")
        assert chain.usage["cerebras"] == 2
        assert "cerebras=2" in chain.stats()

    def test_refuse_une_chaine_vide(self):
        with pytest.raises(ValueError):
            FallbackLLM([])


class FakeClock:
    """Horloge contrôlée : les tests ne dorment jamais réellement."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.now += seconds


class TestRateLimiter:
    def test_laisse_passer_sous_la_limite(self):
        clock = FakeClock()
        limiter = RateLimiter("test", RateLimitConfig(requests_per_minute=5, requests_per_day=100),
                              sleep_fn=clock.sleep, time_fn=clock.monotonic)
        for _ in range(5):
            assert limiter.acquire()
        assert clock.slept == 0

    def test_attend_quand_la_limite_par_minute_est_atteinte(self):
        clock = FakeClock()
        limiter = RateLimiter("test", RateLimitConfig(requests_per_minute=2, requests_per_day=100),
                              sleep_fn=clock.sleep, time_fn=clock.monotonic)
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()  # celui-ci doit provoquer une attente
        assert clock.slept > 55

    def test_refuse_quand_le_quota_journalier_est_epuise(self):
        clock = FakeClock()
        limiter = RateLimiter("test", RateLimitConfig(requests_per_minute=100, requests_per_day=3),
                              sleep_fn=clock.sleep, time_fn=clock.monotonic)
        assert all(limiter.acquire() for _ in range(3))
        # Le quota journalier ne se récupère pas en attendant : on doit basculer.
        assert limiter.acquire() is False

    def test_remaining_today(self):
        limiter = RateLimiter("test", RateLimitConfig(requests_per_minute=60, requests_per_day=10))
        limiter.acquire()
        limiter.acquire()
        assert limiter.remaining_today == 8

    def test_intervalle_minimal_respecte(self):
        clock = FakeClock()
        limiter = RateLimiter("test", RateLimitConfig(requests_per_minute=100, requests_per_day=100,
                                                     min_interval_s=2.0),
                              sleep_fn=clock.sleep, time_fn=clock.monotonic)
        limiter.acquire()
        limiter.acquire()
        assert clock.slept == pytest.approx(2.0, abs=0.1)

    def test_etat_persiste_sur_disque(self, tmp_path):
        state_file = tmp_path / "quota.json"
        first = RateLimiter("test", RateLimitConfig(requests_per_minute=60, requests_per_day=5),
                            state_file=state_file)
        for _ in range(5):
            first.acquire()
        # Un redémarrage du process ne doit pas réinitialiser le quota journalier.
        second = RateLimiter("test", RateLimitConfig(requests_per_minute=60, requests_per_day=5),
                             state_file=state_file)
        assert second.remaining_today == 0
        assert second.acquire() is False
