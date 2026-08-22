"""Tests de l'agent 5 — Technical Reviewer (exactitude technique).

Couvre les deux couches déterministes documentées dans ARCHITECTURE.md
(§6 Sécurité) : détection de secrets en clair et vérification HTTP des liens
cités. La couche LLM (relecture du code/des faits) est simulée par un stub.
"""

from __future__ import annotations

import json

import pytest

from blogseo.application.agents.technical_reviewer import TechnicalReviewerAgent
from blogseo.application.dto.pipeline_state import PipelineState
from blogseo.domain.ports.llm import LLMPort, LLMResponse

EMPTY_LLM_PAYLOAD = {"findings": [], "notes": "rien à signaler"}


class StubLLM(LLMPort):
    name = "stub"

    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload if payload is not None else EMPTY_LLM_PAYLOAD
        self.calls = 0

    def generate(self, system_prompt, user_prompt, *, temperature=0.7, max_output_tokens=4096, json_mode=False):
        self.calls += 1
        return LLMResponse(text=json.dumps(self.payload), provider=self.name, model="stub")

    def is_available(self) -> bool:
        return True


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def build_state(article, *, body: str) -> PipelineState:
    from blogseo.domain.entities.pipeline_run import PipelineRun

    state = PipelineState(run=PipelineRun())
    article.body_markdown = body
    state.article = article
    return state


class TestDetectionDeSecrets:
    @pytest.mark.parametrize("secret,label", [
        ("AIzaSyD1234567890abcdefghijklmno1234567", "clé Google API"),
        ("sk-abcdefghijklmnopqrstuvwx1234", "clé de type OpenAI"),
        ("gsk_abcdefghijklmnopqrstuvwx1234", "clé Groq"),
        ("ghp_abcdefghijklmnopqrstuvwx1234", "token GitHub"),
        ("123456789:AAFabcdefghijklmnopqrstuvwxyz012345", "token de bot Telegram"),
        ("xoxb-1234567890-abcdefghij", "token Slack"),
    ])
    def test_chaque_type_de_secret_est_detecte_et_bloquant(self, article, secret, label):
        agent = TechnicalReviewerAgent(StubLLM(), check_links=False)
        state = build_state(article, body=f"Configurez votre clé : {secret} dans le script.")

        agent.run(state)

        assert state.review.blocking_findings
        assert any(label in f.problem for f in state.review.findings)

    def test_le_secret_n_apparait_pas_en_clair_dans_le_finding(self, article):
        agent = TechnicalReviewerAgent(StubLLM(), check_links=False)
        secret = "sk-abcdefghijklmnopqrstuvwx1234"
        state = build_state(article, body=f"clé : {secret}")

        agent.run(state)

        finding = next(f for f in state.review.findings if "OpenAI" in f.problem)
        assert secret not in finding.excerpt

    def test_aucun_secret_aucune_remarque_deterministe_bloquante(self, article):
        agent = TechnicalReviewerAgent(StubLLM(), check_links=False)
        state = build_state(article, body="Un article tout à fait normal sur n8n, sans secret.")

        agent.run(state)

        assert state.review.blocking_findings == []


class TestVerificationDesLiens:
    def test_lien_valide_n_est_pas_signale_mort(self, article, monkeypatch):
        monkeypatch.setattr("requests.Session.head", lambda self, url, **kw: FakeResponse(200))
        agent = TechnicalReviewerAgent(StubLLM(), check_links=True)
        state = build_state(article, body="Voir https://exemple.com pour plus de détails.")

        agent.run(state)

        assert state.review.broken_urls == []

    def test_lien_mort_est_signale(self, article, monkeypatch):
        monkeypatch.setattr("requests.Session.head", lambda self, url, **kw: FakeResponse(404))
        monkeypatch.setattr("requests.Session.get", lambda self, url, **kw: FakeResponse(404))
        agent = TechnicalReviewerAgent(StubLLM(), check_links=True)
        state = build_state(article, body="Voir https://exemple-mort.com pour plus de détails.")

        agent.run(state)

        assert "https://exemple-mort.com" in state.review.broken_urls

    def test_head_refuse_bascule_sur_get(self, article, monkeypatch):
        """Certains sites refusent HEAD (403/405/501) : on retente en GET avant de conclure."""
        monkeypatch.setattr("requests.Session.head", lambda self, url, **kw: FakeResponse(405))
        monkeypatch.setattr("requests.Session.get", lambda self, url, **kw: FakeResponse(200))
        agent = TechnicalReviewerAgent(StubLLM(), check_links=True)
        state = build_state(article, body="Voir https://exemple.com pour plus de détails.")

        agent.run(state)

        assert state.review.broken_urls == []

    def test_check_links_false_ne_fait_aucun_appel_reseau(self, article, monkeypatch):
        called: list[str] = []
        monkeypatch.setattr(
            "requests.Session.head",
            lambda self, url, **kw: called.append(url) or FakeResponse(200),
        )
        agent = TechnicalReviewerAgent(StubLLM(), check_links=False)
        state = build_state(article, body="Voir https://exemple.com.")

        agent.run(state)

        assert called == []
        assert state.review.checked_urls == {}


class TestRelectureLLM:
    def test_les_remarques_du_llm_sont_integrees_au_verdict(self, article):
        payload = {
            "findings": [
                {"kind": "code_error", "excerpt": "docker run --hello-world", "problem": "Drapeau inexistant",
                 "suggestion": "Utiliser docker run hello-world", "blocking": True},
            ],
            "notes": "Un problème de code relevé.",
        }
        agent = TechnicalReviewerAgent(StubLLM(payload), check_links=False)
        state = build_state(article, body="Contenu normal.")

        agent.run(state)

        assert len(state.review.blocking_findings) == 1
        assert state.review.notes == "Un problème de code relevé."

    def test_kind_inconnu_retombe_sur_factual_error(self, article):
        from blogseo.domain.entities.review import FindingKind

        payload = {"findings": [{"kind": "n_importe_quoi", "problem": "problème", "blocking": False}], "notes": ""}
        agent = TechnicalReviewerAgent(StubLLM(payload), check_links=False)
        state = build_state(article, body="Contenu normal.")

        agent.run(state)

        assert state.review.findings[-1].kind is FindingKind.FACTUAL_ERROR
