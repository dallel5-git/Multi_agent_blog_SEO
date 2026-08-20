"""Tests du Quality Gate — la porte de qualité est 100 % déterministe.

C'est la fonction la plus critique du pipeline : elle décide si un article part
en publication ou repart en réécriture.
"""

from __future__ import annotations

import pytest

from blogseo.application.agents.quality_gate import QualityGateAgent
from blogseo.application.dto.pipeline_state import PipelineState
from blogseo.domain.entities.pipeline_run import PipelineRun
from blogseo.domain.entities.review import FindingKind, ReviewFinding, ReviewResult
from blogseo.domain.entities.topic import Keyword, Topic
from blogseo.domain.value_objects.category import Category

from ..conftest import make_body


@pytest.fixture
def gate() -> QualityGateAgent:
    return QualityGateAgent(min_words=1200, max_words=2000, min_h2=4)


@pytest.fixture
def state(article) -> PipelineState:
    state = PipelineState(run=PipelineRun())
    state.article = article
    state.iteration = 1
    state.topic = Topic(
        title=article.title,
        angle="Contexte tunisien",
        category=Category.N8N,
        primary_keyword=Keyword(term=article.seo.focus_keyword),
        similarity_score=0.2,
    )
    state.review = ReviewResult()
    return state


def _check(state: PipelineState, name: str):
    return next(c for c in state.quality.checks if c.name == name)


class TestArticleConforme:
    def test_un_article_conforme_est_approuve(self, gate, state):
        gate.run(state)
        assert state.quality.approved, state.quality.revision_instructions()
        assert state.quality.score > 0.7
        assert state.revision_instructions == ""


class TestLongueur:
    def test_article_trop_court_est_bloque(self, gate, state):
        state.article.body_markdown = "## Une section\n\nTrop court. Tunisie."
        gate.run(state)
        assert not state.quality.approved
        assert not _check(state, "longueur_minimale").passed
        assert "1200" in state.revision_instructions

    def test_article_trop_long_est_seulement_averti(self, gate, state):
        state.article.body_markdown = make_body(6000)
        gate.run(state)
        assert not _check(state, "longueur_maximale").passed
        assert _check(state, "longueur_maximale").severity.value == "warning"


class TestStructure:
    def test_h1_dans_le_corps_est_bloquant(self, gate, state):
        state.article.body_markdown = "# Un titre H1\n\n" + state.article.body_markdown
        gate.run(state)
        assert not state.quality.approved
        assert not _check(state, "pas_de_h1").passed

    def test_bloc_de_code_non_ferme_est_bloquant(self, gate, state):
        state.article.body_markdown += "\n\n```python\nprint('oups')\n"
        gate.run(state)
        assert not _check(state, "blocs_de_code_equilibres").passed
        assert not state.quality.approved

    def test_pas_assez_de_sections_est_bloquant(self, gate, state):
        state.article.body_markdown = state.article.body_markdown.replace("## ", "### ")
        gate.run(state)
        assert not _check(state, "sections_h2").passed


class TestAngleTunisien:
    def test_absence_d_angle_tunisien_est_bloquante(self, gate, state):
        body = state.article.body_markdown
        for terme in ("Tunisie", "tunisien", "Tunis", "Sfax", "dinar"):
            body = body.replace(terme, "France")
        state.article.body_markdown = body
        gate.run(state)
        assert not _check(state, "angle_tunisien_present").passed
        assert not state.quality.approved
        assert "angle tunisien" in state.revision_instructions.lower()


class TestMotsCles:
    def test_mot_cle_absent_est_bloquant(self, gate, state):
        state.article.body_markdown = state.article.body_markdown.replace("n8n", "zapier")
        state.article.body_markdown = state.article.body_markdown.replace("automatis", "digitalis")
        state.article.body_markdown = state.article.body_markdown.replace("prospection", "vente")
        gate.run(state)
        assert not _check(state, "mot_cle_dans_le_corps").passed

    def test_bourrage_de_mots_cles_est_averti(self, gate, state):
        state.article.body_markdown += "\n\n" + f"{state.article.seo.focus_keyword}. " * 200
        gate.run(state)
        assert not _check(state, "densite_mot_cle").passed
        # Le bourrage seul ne doit pas bloquer la publication.
        assert _check(state, "densite_mot_cle").severity.value == "warning"


class TestIntegrationAvecLesAutresAgents:
    def test_erreur_technique_bloquante_bloque_la_porte(self, gate, state):
        state.review.findings.append(
            ReviewFinding(
                kind=FindingKind.CODE_ERROR,
                excerpt="eval(user_input)",
                problem="Exécution de code arbitraire",
                suggestion="Utiliser ast.literal_eval",
                blocking=True,
            )
        )
        gate.run(state)
        assert not _check(state, "relecture_technique").passed
        assert not state.quality.approved
        assert "Exécution de code arbitraire" in state.revision_instructions

    def test_lien_mort_est_seulement_averti(self, gate, state):
        state.review.checked_urls = {"https://exemple.invalide": False}
        gate.run(state)
        assert not _check(state, "liens_valides").passed
        assert state.quality.approved  # non bloquant

    def test_sujet_doublon_est_bloquant(self, gate, state):
        state.topic.similarity_score = 0.95
        state.topic.similar_slug = "automatiser-workflows-n8n"
        gate.run(state)
        assert not _check(state, "originalite_sujet").passed
        assert not state.quality.approved


class TestRapport:
    def test_le_score_est_un_ratio(self, gate, state):
        gate.run(state)
        assert 0.0 <= state.quality.score <= 1.0

    def test_les_consignes_sont_vides_si_approuve(self, gate, state):
        gate.run(state)
        assert state.quality.revision_instructions() == ""

    def test_les_consignes_distinguent_bloquant_et_amelioration(self, gate, state):
        state.article.body_markdown = "## Section\n\nCourt."
        gate.run(state)
        instructions = state.quality.revision_instructions()
        assert "[BLOQUANT]" in instructions
