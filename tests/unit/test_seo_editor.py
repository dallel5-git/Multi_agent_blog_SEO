"""Tests de l'agent 6 — SEO Editor (métadonnées, slug, maillage interne).

Agent critique : le LLM propose, mais c'est la partie déterministe
(`_fix_*`) qui garantit qu'aucune métadonnée non conforme ne sort de
l'agent — c'est elle qu'on teste ici en priorité.
"""

from __future__ import annotations

import json

from blogseo.application.agents.seo_editor import SeoEditorAgent
from blogseo.application.dto.pipeline_state import PipelineState
from blogseo.domain.entities.pipeline_run import PipelineRun
from blogseo.domain.entities.topic import Keyword, Topic
from blogseo.domain.ports.llm import LLMPort, LLMResponse
from blogseo.domain.ports.repositories import PublishedArticleRef
from blogseo.domain.value_objects.category import Category
from blogseo.domain.value_objects.seo_metadata import DESCRIPTION_MAX, TITLE_MAX


class StubLLM(LLMPort):
    name = "stub"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def generate(self, system_prompt, user_prompt, *, temperature=0.7, max_output_tokens=4096, json_mode=False):
        self.calls.append(user_prompt)
        return LLMResponse(text=json.dumps(self.payload), provider=self.name, model="stub")

    def is_available(self) -> bool:
        return True


GOOD_PAYLOAD = {
    "meta_title": "Automatiser sa prospection avec n8n en Tunisie",
    "meta_description": (
        "Guide pratique pour automatiser votre prospection commerciale avec n8n, "
        "pensé pour les PME et freelances tunisiens : installation gratuite et workflow complet."
    ),
    "slug": "automatiser-prospection-n8n",
    "focus_keyword": "prospection avec n8n",
    "secondary_keywords": ["n8n Tunisie", "automatisation PME"],
    "cover_alt_text": "Illustration du workflow n8n",
    "internal_links": ["article-existant"],
    "tags": ["n8n", "automatisation", "tunisie"],
}


def build_state(article, *, existing_slugs: tuple[str, ...] = ("article-existant",)) -> PipelineState:
    state = PipelineState(run=PipelineRun())
    state.article = article
    state.topic = Topic(
        title=article.title, angle="Angle tunisien", category=Category.N8N,
        primary_keyword=Keyword(term="prospection avec n8n"),
        secondary_keywords=(Keyword(term="n8n Tunisie", priority=2), Keyword(term="pme tunisienne", priority=3)),
    )
    state.existing_articles = [
        PublishedArticleRef(slug=slug, title=f"Titre {slug}") for slug in existing_slugs
    ]
    return state


class TestRunConforme:
    def test_article_conforme_est_produit(self, article):
        agent = SeoEditorAgent(StubLLM(GOOD_PAYLOAD))
        state = build_state(article)

        agent.run(state)

        assert state.article.seo.focus_keyword == "prospection avec n8n"
        assert state.article.slug.value == "automatiser-prospection-n8n"
        assert not state.article.seo.all_issues()

    def test_lien_interne_valide_est_injecte_dans_le_corps(self, article):
        agent = SeoEditorAgent(StubLLM(GOOD_PAYLOAD))
        state = build_state(article)

        agent.run(state)

        assert "## À lire aussi" in state.article.body_markdown
        assert "/blog/article-existant" in state.article.body_markdown


class TestLiensInternesInventes:
    def test_slug_inexistant_est_retire(self, article):
        payload = {**GOOD_PAYLOAD, "internal_links": ["article-existant", "slug-invente-par-le-llm"]}
        agent = SeoEditorAgent(StubLLM(payload))
        state = build_state(article, existing_slugs=("article-existant",))

        agent.run(state)

        assert state.article.seo.internal_links == ("article-existant",)
        assert "slug-invente-par-le-llm" not in state.article.body_markdown

    def test_respecte_la_limite_max_internal_links(self, article):
        payload = {**GOOD_PAYLOAD, "internal_links": ["a", "b", "c", "d"]}
        agent = SeoEditorAgent(StubLLM(payload), max_internal_links=2)
        state = build_state(article, existing_slugs=("a", "b", "c", "d"))

        agent.run(state)

        assert len(state.article.seo.internal_links) == 2


class TestCollisionDeSlug:
    def test_slug_deja_pris_est_suffixe(self, article):
        payload = {**GOOD_PAYLOAD, "slug": "article-existant"}
        agent = SeoEditorAgent(StubLLM(payload))
        state = build_state(article, existing_slugs=("article-existant",))

        agent.run(state)

        assert state.article.slug.value == "article-existant-2"

    def test_slug_libre_n_est_pas_touche(self, article):
        agent = SeoEditorAgent(StubLLM(GOOD_PAYLOAD))
        state = build_state(article, existing_slugs=())

        agent.run(state)

        assert state.article.slug.value == "automatiser-prospection-n8n"


class TestTitre:
    def test_mot_cle_absent_est_prefixe_si_ca_tient(self, article):
        payload = {**GOOD_PAYLOAD, "meta_title": "Le guide complet pour les PME"}
        agent = SeoEditorAgent(StubLLM(payload))
        state = build_state(article)

        agent.run(state)

        assert "prospection avec n8n" in state.article.seo.meta_title.lower()
        assert len(state.article.seo.meta_title) <= TITLE_MAX

    def test_titre_trop_long_est_tronque_sans_casser_la_limite(self, article):
        payload = {**GOOD_PAYLOAD, "meta_title": "x" * 90}
        agent = SeoEditorAgent(StubLLM(payload))
        state = build_state(article)

        agent.run(state)

        assert len(state.article.seo.meta_title) <= TITLE_MAX


class TestDescription:
    def test_description_trop_courte_est_completee(self, article):
        payload = {**GOOD_PAYLOAD, "meta_description": "Trop court."}
        agent = SeoEditorAgent(StubLLM(payload))
        state = build_state(article)

        agent.run(state)

        assert len(state.article.seo.meta_description) >= 60  # nettement rallongée, sans viser un seuil exact

    def test_description_trop_longue_reste_sous_la_limite(self, article):
        payload = {**GOOD_PAYLOAD, "meta_description": "d " * 100}
        agent = SeoEditorAgent(StubLLM(payload))
        state = build_state(article)

        agent.run(state)

        assert len(state.article.seo.meta_description) <= DESCRIPTION_MAX


class TestTags:
    def test_moins_de_trois_tags_est_complete_avec_les_mots_cles_du_sujet(self, article):
        payload = {**GOOD_PAYLOAD, "tags": ["n8n"]}
        agent = SeoEditorAgent(StubLLM(payload))
        state = build_state(article)

        agent.run(state)

        assert len(state.article.tags) >= 3

    def test_tags_deja_suffisants_sont_conserves_tels_quels(self, article):
        agent = SeoEditorAgent(StubLLM(GOOD_PAYLOAD))
        state = build_state(article)

        agent.run(state)

        assert set(state.article.tags) == {"n8n", "automatisation", "tunisie"}


class TestMaillageIdempotent:
    def test_ne_duplique_pas_la_section_deja_presente(self, article):
        article.body_markdown += "\n\n## À lire aussi\n\n- [Déjà là](/blog/deja-la)\n"
        agent = SeoEditorAgent(StubLLM(GOOD_PAYLOAD))
        state = build_state(article)

        agent.run(state)

        assert state.article.body_markdown.count("## À lire aussi") == 1
