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
from blogseo.domain.entities.series import ArticleSeries, SeriesTopic
from blogseo.domain.errors import DuplicateTopicError
from blogseo.domain.ports.llm import LLMPort, LLMResponse
from blogseo.domain.ports.repositories import (
    ArticleHistoryPort,
    PublishedArticleRef,
    SeriesRepositoryPort,
    SimilarityHit,
)
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


# --------------------------------------------------------------------------- #
# Mode série (issue #41)
# --------------------------------------------------------------------------- #

class PayloadLLM(LLMPort):
    """Renvoie une liste de payloads JSON complets, un par appel (batch ou retry)."""

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


class FakeSeriesRepository(SeriesRepositoryPort):
    def __init__(self, active: ArticleSeries | None = None) -> None:
        self._by_id = {active.series_id: active} if active else {}
        self.saved: list[ArticleSeries] = []

    def save(self, series: ArticleSeries) -> None:
        self._by_id[series.series_id] = series
        self.saved.append(series)

    def get(self, series_id: str) -> ArticleSeries | None:
        return self._by_id.get(series_id)

    def find_active(self) -> ArticleSeries | None:
        for series in self._by_id.values():
            if series.is_active:
                return series
        return None

    def list_all(self) -> list[ArticleSeries]:
        return list(self._by_id.values())


def series_topic_payload(title: str, category: str = "n8n") -> dict:
    return {
        "title": title,
        "angle": "Angle tunisien concret.",
        "category": category,
        "primary_keyword": f"mot-clé {title}",
        "secondary_keywords": ["secondaire"],
        "outline": ["Introduction", "Mise en place", "Conclusion"],
        "rationale": "Pertinent pour cet épisode de la série.",
    }


def series_batch_payload(titles: list[str]) -> dict:
    return {
        "series_title": "Automatiser sa PME avec n8n",
        "topics": [series_topic_payload(t) for t in titles],
    }


def series_batch_payload_with_category(title: str, category: str) -> dict:
    return {"series_title": "Automatiser sa PME avec n8n", "topics": [series_topic_payload(title, category)]}


def make_pending_series(size: int = 1) -> ArticleSeries:
    return ArticleSeries(
        theme="n8n",
        title="Automatiser sa PME avec n8n",
        topics=[
            SeriesTopic(
                title=f"Épisode {i}", angle="angle", category=Category.N8N,
                primary_keyword=f"mot-clé {i}",
            )
            for i in range(1, size + 1)
        ],
    )


class TestPlanSeries:
    def test_planifie_size_sujets_en_un_seul_appel_llm(self):
        llm = PayloadLLM([series_batch_payload(["Découverte", "Mise en place", "Cas avancé"])])
        history = FakeHistory([ORIGINAL_HIT, ORIGINAL_HIT, ORIGINAL_HIT])
        repo = FakeSeriesRepository()
        agent = KeywordAnalystAgent(llm, history, series_repository=repo)

        series = agent.plan_series(make_state(), theme="n8n", size=3)

        assert len(llm.calls) == 1
        assert len(series.topics) == 3
        assert [t.title for t in series.topics] == ["Découverte", "Mise en place", "Cas avancé"]
        assert series.title == "Automatiser sa PME avec n8n"
        assert repo.saved and repo.saved[-1].series_id == series.series_id

    def test_categorie_libre_est_ramenee_a_l_union_fermee(self):
        llm = PayloadLLM([series_batch_payload_with_category("Sujet", "Automatisation")])
        history = FakeHistory([ORIGINAL_HIT])
        repo = FakeSeriesRepository()
        agent = KeywordAnalystAgent(llm, history, series_repository=repo)

        series = agent.plan_series(make_state(), theme="n8n", size=1)

        assert series.topics[0].category == Category.N8N

    def test_doublon_sur_un_creneau_redemande_un_remplacant(self):
        llm = PayloadLLM([
            series_batch_payload(["Sujet doublon", "Sujet original"]),
            series_batch_payload(["Sujet remplaçant"]),  # réponse du retry pour le créneau 1
        ])
        history = FakeHistory([DUPLICATE_HIT, ORIGINAL_HIT, ORIGINAL_HIT])
        repo = FakeSeriesRepository()
        agent = KeywordAnalystAgent(llm, history, series_repository=repo, max_attempts=3)

        series = agent.plan_series(make_state(), theme="n8n", size=2)

        assert len(llm.calls) == 2
        assert series.topics[0].title == "Sujet remplaçant"
        assert series.topics[1].title == "Sujet original"


class TestRunConsommeLaFileDAttente:
    def test_sujet_en_attente_utilise_sans_appel_llm(self):
        llm = PayloadLLM([topic_payload("ne devrait jamais être appelé")])
        history = FakeHistory([ORIGINAL_HIT])
        series = make_pending_series(size=2)
        repo = FakeSeriesRepository(series)
        agent = KeywordAnalystAgent(llm, history, series_repository=repo)

        state = agent.run(make_state())

        assert llm.calls == []
        assert state.topic.title == "Épisode 1"
        assert state.series_id == series.series_id
        assert state.series_topic_index == 0

    def test_sujet_devenu_doublon_retombe_sur_la_generation_normale(self):
        llm = PayloadLLM([topic_payload("Sujet frais généré normalement")])
        history = FakeHistory([DUPLICATE_HIT, ORIGINAL_HIT])
        series = make_pending_series(size=1)
        repo = FakeSeriesRepository(series)
        agent = KeywordAnalystAgent(llm, history, series_repository=repo)

        state = agent.run(make_state())

        assert len(llm.calls) == 1
        assert state.topic.title == "Sujet frais généré normalement"
        assert state.series_id == ""
        assert series.topics[0].status == "skipped"

    def test_sans_serie_active_generation_normale_inchangee(self):
        llm = PayloadLLM([topic_payload("Sujet isolé")])
        history = FakeHistory([ORIGINAL_HIT])
        repo = FakeSeriesRepository(active=None)
        agent = KeywordAnalystAgent(llm, history, series_repository=repo)

        state = agent.run(make_state())

        assert len(llm.calls) == 1
        assert state.topic.title == "Sujet isolé"
        assert state.series_id == ""
