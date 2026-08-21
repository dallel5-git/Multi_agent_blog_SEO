"""Tests de l'agent 3 — Keyword Analyst (sujet + anti-doublon).

On simule le LLM et le vector store pour vérifier, au niveau de l'agent, les
critères d'acceptation de l'issue « Agent 3 — Keyword Analyst » : catégorie
toujours dans l'union fermée, doublon refusé et redemandé avec une
température croissante, `DuplicateTopicError` explicite après 3 échecs.
"""

from __future__ import annotations

import json

import pytest

from blogseo.application.agents.keyword_analyst import KeywordAnalystAgent
from blogseo.application.dto.pipeline_state import PipelineState
from blogseo.domain.entities.pipeline_run import PipelineRun
from blogseo.domain.errors import DuplicateTopicError
from blogseo.domain.ports.llm import LLMPort, LLMResponse
from blogseo.domain.ports.repositories import ArticleHistoryPort, PublishedArticleRef, SimilarityHit
from blogseo.domain.value_objects.category import Category


class FakeLLM(LLMPort):
    """Renvoie une réponse JSON pré-écrite par appel, capture la température reçue."""

    name = "fake"

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads
        self.calls: list[float] = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        self.calls.append(temperature)
        payload = self._payloads[len(self.calls) - 1]
        return LLMResponse(text=json.dumps(payload), provider="fake", model="fake")


class FakeHistory(ArticleHistoryPort):
    """Renvoie une liste de voisins pré-écrite par appel à `find_similar`."""

    def __init__(self, hits_per_call: list[list[SimilarityHit]]) -> None:
        self._hits_per_call = hits_per_call
        self.calls = 0

    def index(self, articles: list[PublishedArticleRef]) -> int:
        return len(articles)

    def find_similar(self, text: str, *, top_k: int = 3) -> list[SimilarityHit]:
        hits = self._hits_per_call[self.calls]
        self.calls += 1
        return hits

    def count(self) -> int:
        return 0


def make_state() -> PipelineState:
    return PipelineState(run=PipelineRun())


def topic_payload(title: str, category: str = "n8n") -> dict:
    return {
        "title": title,
        "angle": "Angle tunisien concret.",
        "category": category,
        "primary_keyword": {"term": f"mot-clé {title}", "intent": "tutorial"},
        "secondary_keywords": [{"term": "mot-clé secondaire", "intent": "informational"}],
        "rationale": "Pertinent maintenant.",
        "outline": ["Introduction", "Mise en place", "Conclusion"],
        "sources": ["https://example.com"],
    }


DUPLICATE_HIT = [SimilarityHit(slug="article-existant", title="Article existant", score=0.93)]
ORIGINAL_HIT: list[SimilarityHit] = []


class TestSujetOriginal:
    def test_premiere_tentative_reussie(self):
        llm = FakeLLM([topic_payload("Automatiser la prospection avec n8n en Tunisie")])
        history = FakeHistory([ORIGINAL_HIT])
        agent = KeywordAnalystAgent(llm, history, duplicate_threshold=0.85, max_attempts=3)

        state = agent.run(make_state())

        assert state.topic is not None
        assert state.topic.title == "Automatiser la prospection avec n8n en Tunisie"
        assert isinstance(state.topic.category, Category)
        assert len(llm.calls) == 1
        assert llm.calls[0] == pytest.approx(0.4)


class TestCategorieToujoursValide:
    def test_categorie_libre_est_ramenee_a_l_union_fermee(self):
        llm = FakeLLM([topic_payload("Sujet quelconque", category="Automatisation")])
        history = FakeHistory([ORIGINAL_HIT])
        agent = KeywordAnalystAgent(llm, history)

        state = agent.run(make_state())

        assert state.topic.category in list(Category)
        assert state.topic.category == Category.N8N  # alias connu de "Automatisation"


class TestDoublonRefuseEtRedemande:
    def test_doublon_puis_sujet_original_a_la_deuxieme_tentative(self):
        llm = FakeLLM([
            topic_payload("Sujet déjà couvert"),
            topic_payload("Sujet vraiment nouveau"),
        ])
        history = FakeHistory([DUPLICATE_HIT, ORIGINAL_HIT])
        agent = KeywordAnalystAgent(llm, history, duplicate_threshold=0.85, max_attempts=3, temperature=0.4)

        state = agent.run(make_state())

        assert len(llm.calls) == 2
        assert llm.calls[1] > llm.calls[0]
        assert llm.calls[1] == pytest.approx(0.6)
        assert state.rejected_titles == ["Sujet déjà couvert (≈ article-existant)"]
        assert state.topic.title == "Sujet vraiment nouveau"


class TestEchecApresTroisTentatives:
    def test_trois_doublons_leve_duplicate_topic_error(self):
        llm = FakeLLM([
            topic_payload("Sujet 1"),
            topic_payload("Sujet 2"),
            topic_payload("Sujet 3"),
        ])
        history = FakeHistory([DUPLICATE_HIT, DUPLICATE_HIT, DUPLICATE_HIT])
        agent = KeywordAnalystAgent(llm, history, duplicate_threshold=0.85, max_attempts=3, temperature=0.4)

        with pytest.raises(DuplicateTopicError) as exc_info:
            agent.run(make_state())

        assert len(llm.calls) == 3
        assert llm.calls == pytest.approx([0.4, 0.6, 0.8])
        error = exc_info.value
        assert error.title == "Sujet 3"
        assert error.similar_slug == "article-existant"
        assert error.score == pytest.approx(0.93)
