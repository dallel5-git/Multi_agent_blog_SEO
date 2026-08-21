"""Tests de l'agent 10 — Social Writer (issue #40).

Critères d'acceptation vérifiés :
- ne s'exécute (génération + notification) que si l'article a réellement
  été publié (`RunStatus.PUBLISHED`) ;
- aucune publication automatique : le seul canal de sortie est
  `NotifierPort.send()`, jamais un appel réseau vers LinkedIn/X.
"""

from __future__ import annotations

import json

from blogseo.application.agents.social_writer import SocialWriterAgent
from blogseo.application.dto.pipeline_state import PipelineState
from blogseo.domain.entities.article import Article
from blogseo.domain.entities.pipeline_run import PipelineRun, RunStatus
from blogseo.domain.entities.topic import Keyword, Topic
from blogseo.domain.ports.llm import LLMResponse
from blogseo.domain.value_objects.category import Category
from blogseo.domain.value_objects.seo_metadata import SeoMetadata
from blogseo.domain.value_objects.slug import Slug


class StubLLM:
    name = "stub"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt, user_prompt, *, temperature=0.7, max_output_tokens=4096, json_mode=False):
        self.calls.append((system_prompt, user_prompt))
        return LLMResponse(text=self.text, provider=self.name, model="stub")

    def is_available(self) -> bool:
        return True


class SpyNotifier:
    name = "spy"

    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str, *, silent: bool = False) -> bool:
        self.messages.append(text)
        return True

    def send_document(self, path, caption: str = "") -> bool:  # pragma: no cover - non utilisé ici
        return True


VALID_PAYLOAD = json.dumps({
    "linkedin_post": "Automatiser sa prospection change tout pour une PME tunisienne.\n#n8n #automatisation",
    "x_thread": [
        "Vous perdez des heures chaque semaine à relancer vos contacts à la main ?",
        "n8n permet d'automatiser tout ça, gratuitement.",
        "Lisez l'article complet pour le workflow pas à pas.",
    ],
})


def build_state(*, status: RunStatus) -> PipelineState:
    state = PipelineState(run=PipelineRun())
    state.run.finish(status)
    state.article = Article(
        title="Automatiser sa prospection avec n8n",
        slug=Slug("automatiser-prospection-n8n"),
        body_markdown=(
            "Intro.\n\n## Pourquoi automatiser\ncontenu\n\n## Installer n8n\ncontenu"
        ),
        seo=SeoMetadata(
            meta_title="Automatiser sa prospection avec n8n en Tunisie",
            meta_description="Guide pratique pour les PME tunisiennes.",
            focus_keyword="prospection n8n",
        ),
        category=Category.N8N,
    )
    state.topic = Topic(
        title="Automatiser sa prospection avec n8n",
        angle="Les PME tunisiennes perdent du temps sur la relance manuelle.",
        category=Category.N8N,
        primary_keyword=Keyword(term="prospection n8n"),
    )
    return state


class TestNeSExecuteQueSiPublie:
    def test_article_reste_en_local_ne_genere_rien(self):
        llm = StubLLM(VALID_PAYLOAD)
        notifier = SpyNotifier()
        agent = SocialWriterAgent(llm, notifier)

        state = agent.run(build_state(status=RunStatus.SAVED_LOCALLY))

        assert llm.calls == []
        assert notifier.messages == []
        assert state.linkedin_post == ""
        assert state.x_thread == ()

    def test_run_en_echec_ne_genere_rien(self):
        llm = StubLLM(VALID_PAYLOAD)
        notifier = SpyNotifier()
        agent = SocialWriterAgent(llm, notifier)

        agent.run(build_state(status=RunStatus.FAILED))

        assert llm.calls == []
        assert notifier.messages == []

    def test_article_publie_genere_le_contenu(self):
        llm = StubLLM(VALID_PAYLOAD)
        notifier = SpyNotifier()
        agent = SocialWriterAgent(llm, notifier, blog_url="https://exemple.com")

        state = agent.run(build_state(status=RunStatus.PUBLISHED))

        assert len(llm.calls) == 1
        assert "Automatiser sa prospection change tout" in state.linkedin_post
        assert len(state.x_thread) == 3


class TestAucunePublicationAutomatique:
    def test_le_seul_canal_de_sortie_est_le_notifier(self):
        llm = StubLLM(VALID_PAYLOAD)
        notifier = SpyNotifier()
        agent = SocialWriterAgent(llm, notifier, blog_url="https://exemple.com")

        agent.run(build_state(status=RunStatus.PUBLISHED))

        assert len(notifier.messages) == 1
        message = notifier.messages[0]
        assert "copier-coller manuel" in message
        assert "LinkedIn" in message
        assert "Thread X" in message
        assert "https://exemple.com/blog/automatiser-prospection-n8n" in message

    def test_sans_notifier_ne_leve_pas(self):
        llm = StubLLM(VALID_PAYLOAD)
        agent = SocialWriterAgent(llm, notifier=None)

        state = agent.run(build_state(status=RunStatus.PUBLISHED))

        assert state.linkedin_post  # le contenu est bien généré même sans canal de sortie


class TestDegradationGracieuse:
    def test_reponse_llm_vide_ne_notifie_pas_et_avertit(self):
        llm = StubLLM(json.dumps({"linkedin_post": "", "x_thread": []}))
        notifier = SpyNotifier()
        agent = SocialWriterAgent(llm, notifier)

        state = agent.run(build_state(status=RunStatus.PUBLISHED))

        assert notifier.messages == []
        assert any("aucun contenu" in w.lower() for w in state.warnings)

    def test_reponse_non_json_ne_leve_pas(self):
        llm = StubLLM("réponse inexploitable, pas du JSON")
        notifier = SpyNotifier()
        agent = SocialWriterAgent(llm, notifier)

        state = agent.run(build_state(status=RunStatus.PUBLISHED))

        assert state.linkedin_post == ""
        assert notifier.messages == []


class TestContenuDuPrompt:
    def test_les_sections_h2_de_l_article_sont_transmises(self):
        llm = StubLLM(VALID_PAYLOAD)
        agent = SocialWriterAgent(llm, SpyNotifier())

        agent.run(build_state(status=RunStatus.PUBLISHED))

        _, user_prompt = llm.calls[0]
        assert "Pourquoi automatiser" in user_prompt
        assert "Installer n8n" in user_prompt

    def test_angle_tunisien_du_topic_est_transmis(self):
        llm = StubLLM(VALID_PAYLOAD)
        agent = SocialWriterAgent(llm, SpyNotifier())

        agent.run(build_state(status=RunStatus.PUBLISHED))

        _, user_prompt = llm.calls[0]
        assert "relance manuelle" in user_prompt


def test_describe_sans_contenu():
    agent = SocialWriterAgent(StubLLM(""), SpyNotifier())
    state = build_state(status=RunStatus.SAVED_LOCALLY)
    assert "aucun contenu" in agent.describe(state)


def test_describe_avec_contenu():
    agent = SocialWriterAgent(StubLLM(VALID_PAYLOAD), SpyNotifier())
    state = agent.run(build_state(status=RunStatus.PUBLISHED))
    description = agent.describe(state)
    assert "LinkedIn" in description
    assert "3 tweet" in description
