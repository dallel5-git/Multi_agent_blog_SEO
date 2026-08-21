"""Tests du tableau de bord HTML local des runs (issue #39).

Critères d'acceptation vérifiés : la page s'ouvre sans serveur (HTML
statique bien formé) et met en évidence les runs en échec et les articles
restés non publiés (`SAVED_LOCALLY`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

from blogseo.domain.entities.pipeline_run import Decision, PipelineRun, RunStatus
from blogseo.interfaces.dashboard import render_dashboard, write_dashboard

_VOID_TAGS = {"meta", "link", "br", "img", "hr", "input"}


class _WellFormedChecker(HTMLParser):
    """Vérifie que chaque balise ouvrante a bien sa fermante correspondante."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in _VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack[-1] == tag, f"balise mal fermée : {tag}"
        self.stack.pop()


def assert_well_formed(html: str) -> None:
    checker = _WellFormedChecker()
    checker.feed(html)
    assert checker.stack == [], f"balises jamais fermées : {checker.stack}"


def make_run(
    *,
    status: RunStatus = RunStatus.PUBLISHED,
    topic: str = "Sujet de test",
    quality: float = 0.9,
    decision: Decision | None = None,
    started_ago_days: int = 0,
    errors: list[str] | None = None,
) -> PipelineRun:
    run = PipelineRun(
        run_id=f"run-{status.value}-{started_ago_days}",
        started_at=datetime.now(UTC) - timedelta(days=started_ago_days, minutes=5),
        topic_title=topic,
        quality_score=quality,
        decision=decision,
        errors=errors or [],
    )
    trace = run.start_step("content_writer")
    run.end_step(trace, ok=not errors, detail="1500 mots")
    run.finish(status)
    return run


class TestPageVide:
    def test_aucun_run_ne_leve_pas(self):
        html = render_dashboard([])
        assert_well_formed(html)
        assert "Aucun run enregistré" in html


class TestFormatHtml:
    def test_page_bien_formee_avec_plusieurs_runs(self):
        runs = [
            make_run(status=RunStatus.PUBLISHED, decision=Decision.APPROVE),
            make_run(status=RunStatus.SAVED_LOCALLY, decision=Decision.REJECT, started_ago_days=1),
            make_run(status=RunStatus.FAILED, errors=["content_writer: timeout"], started_ago_days=2),
        ]
        html = render_dashboard(runs)
        assert_well_formed(html)
        assert "<!doctype html>" in html.lower()

    def test_ouvrable_sans_serveur_aucune_dependance_externe(self):
        html = render_dashboard([make_run()])
        # Pas de <script src=...>, <link rel="stylesheet" href=...> externe, etc.
        assert "http://" not in html.replace('file://', '')
        assert "https://" not in html
        assert "<script" not in html  # tout est en <details> natif, pas de JS


class TestEchappementHtml:
    def test_titre_avec_caracteres_speciaux_est_echappe(self):
        run = make_run(topic="<script>alert('x')</script> & \"citation\"")
        html = render_dashboard([run])
        assert_well_formed(html)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_erreur_avec_caracteres_speciaux_est_echappee(self):
        run = make_run(status=RunStatus.FAILED, errors=["<img src=x onerror=alert(1)>"])
        html = render_dashboard([run])
        assert_well_formed(html)
        assert "<img src=x" not in html


class TestMiseEnEvidence:
    def test_run_en_echec_est_signale(self):
        run = make_run(status=RunStatus.FAILED, errors=["boom"])
        html = render_dashboard([run])
        assert 'class="row-fail"' in html
        assert "✖ Échec" in html

    def test_article_reste_non_publie_est_signale(self):
        run = make_run(status=RunStatus.SAVED_LOCALLY)
        html = render_dashboard([run])
        assert 'class="row-warn"' in html
        assert "En local" in html

    def test_run_publie_n_est_pas_signale_comme_probleme(self):
        run = make_run(status=RunStatus.PUBLISHED)
        html = render_dashboard([run])
        assert 'class="row-fail"' not in html
        assert 'class="row-warn"' not in html


class TestKpisEtDurees:
    def test_compte_les_statuts_correctement(self):
        runs = [
            make_run(status=RunStatus.PUBLISHED),
            make_run(status=RunStatus.PUBLISHED, started_ago_days=1),
            make_run(status=RunStatus.SAVED_LOCALLY, started_ago_days=2),
            make_run(status=RunStatus.FAILED, errors=["x"], started_ago_days=3),
        ]
        html = render_dashboard(runs)
        assert ">4<" in html  # total runs
        assert "Durée moyenne par agent" in html
        assert "content_writer" in html

    def test_runs_tries_du_plus_recent_au_plus_ancien(self):
        older = make_run(topic="Ancien sujet", started_ago_days=5)
        newer = make_run(topic="Sujet récent", started_ago_days=0)
        html = render_dashboard([older, newer])
        assert html.index("Sujet récent") < html.index("Ancien sujet")


class TestEcritureSurDisque:
    def test_write_dashboard_cree_le_dossier_et_le_fichier(self, tmp_path):
        output = tmp_path / "sous-dossier" / "dashboard.html"
        written = write_dashboard([make_run()], output)
        assert written == output
        assert output.exists()
        assert "<!doctype html>" in output.read_text(encoding="utf-8").lower()
