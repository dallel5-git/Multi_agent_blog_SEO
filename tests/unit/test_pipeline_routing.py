"""Tests des boucles de feedback du graphe (routage conditionnel)."""

from __future__ import annotations

from blogseo.application.dto.pipeline_state import PipelineState
from blogseo.domain.entities.pipeline_run import Decision, PipelineRun
from blogseo.domain.value_objects.quality_report import QualityCheck, QualityReport, Severity
from blogseo.orchestrator.pipeline_spec import (
    LINEAR_EDGES,
    route_after_publisher,
    route_after_quality_gate,
)

APPROVED = QualityReport(checks=(QualityCheck("ok", True, Severity.BLOCKER),))
REJECTED = QualityReport(
    checks=(QualityCheck("longueur", False, Severity.BLOCKER, "trop court"),)
)


def state_with(quality: QualityReport | None, iteration: int = 1) -> PipelineState:
    state = PipelineState(run=PipelineRun())
    state.quality = quality
    state.iteration = iteration
    return state


class TestBoucleQualityGate:
    def test_article_approuve_va_au_publisher(self):
        assert route_after_quality_gate(state_with(APPROVED), max_revisions=2) == "publisher"

    def test_article_rejete_retourne_au_redacteur(self):
        assert route_after_quality_gate(state_with(REJECTED, 1), max_revisions=2) == "content_writer"

    def test_boucle_bornee_par_max_revisions(self):
        # Après max_revisions + 1 rédactions, on cesse de boucler.
        state = state_with(REJECTED, iteration=3)
        assert route_after_quality_gate(state, max_revisions=2) == "publisher"
        assert state.warnings  # l'échec persistant est signalé

    def test_absence_de_rapport_ne_bloque_pas(self):
        assert route_after_quality_gate(state_with(None), max_revisions=2) == "publisher"


class TestBouclePublisher:
    def test_bouton_reecrire_renvoie_au_redacteur(self):
        state = state_with(APPROVED, iteration=1)
        state.run.decision = Decision.REWRITE
        assert route_after_publisher(state, max_revisions=2) == "content_writer"

    def test_publication_va_au_social_writer(self):
        state = state_with(APPROVED)
        state.run.decision = Decision.APPROVE
        assert route_after_publisher(state, max_revisions=2) == "social_writer"

    def test_enregistrement_local_va_au_social_writer(self):
        state = state_with(APPROVED)
        state.run.decision = Decision.REJECT
        assert route_after_publisher(state, max_revisions=2) == "social_writer"

    def test_reecriture_est_bornee(self):
        state = state_with(APPROVED, iteration=99)
        state.run.decision = Decision.REWRITE
        assert route_after_publisher(state, max_revisions=2) == "social_writer"


class TestTopologieAgent10:
    """Le Social Writer (issue #40) s'insère entre Publisher et Analytics Tracker."""

    def test_social_writer_enchaine_sur_analytics_tracker(self):
        assert LINEAR_EDGES["social_writer"] == "analytics_tracker"

    def test_publisher_n_a_plus_d_arete_lineaire_directe(self):
        # Le Publisher est routé conditionnellement (route_after_publisher), pas
        # via LINEAR_EDGES : s'il y apparaissait, l'arête serait ignorée en silence.
        assert "publisher" not in LINEAR_EDGES
