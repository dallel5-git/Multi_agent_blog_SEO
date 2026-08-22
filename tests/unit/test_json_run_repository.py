"""Tests de la persistance JSON des runs (nécessaire à la validation humaine différée)."""

from __future__ import annotations

import time

from blogseo.domain.entities.pipeline_run import Decision, PipelineRun, RunStatus
from blogseo.infrastructure.persistence.json_run_repository import JsonRunRepository


def make_run(*, status: RunStatus = RunStatus.RUNNING) -> PipelineRun:
    run = PipelineRun(topic_title="Un sujet", article_slug="un-sujet")
    trace = run.start_step("bootstrap")
    run.end_step(trace, ok=True, detail="ok")
    run.status = status
    return run


class TestRoundTrip:
    def test_save_puis_get_restitue_le_run(self, tmp_path):
        repo = JsonRunRepository(tmp_path)
        run = make_run()
        run.decision = Decision.APPROVE

        repo.save(run)
        loaded = repo.get(run.run_id)

        assert loaded is not None
        assert loaded.run_id == run.run_id
        assert loaded.topic_title == "Un sujet"
        assert loaded.article_slug == "un-sujet"
        assert loaded.decision is Decision.APPROVE
        assert len(loaded.steps) == 1
        assert loaded.steps[0].name == "bootstrap"
        assert loaded.steps[0].ok

    def test_get_inexistant_renvoie_none(self, tmp_path):
        repo = JsonRunRepository(tmp_path)
        assert repo.get("run-inconnu") is None

    def test_run_sans_decision_est_relu_a_none(self, tmp_path):
        repo = JsonRunRepository(tmp_path)
        run = make_run()

        repo.save(run)
        loaded = repo.get(run.run_id)

        assert loaded.decision is None


class TestListAwaitingReview:
    def test_ne_renvoie_que_les_runs_en_attente(self, tmp_path):
        repo = JsonRunRepository(tmp_path)
        waiting = make_run(status=RunStatus.AWAITING_REVIEW)
        published = make_run(status=RunStatus.PUBLISHED)
        repo.save(waiting)
        repo.save(published)

        result = repo.list_awaiting_review()

        assert [r.run_id for r in result] == [waiting.run_id]


class TestListRecent:
    def test_trie_du_plus_recent_au_plus_ancien(self, tmp_path):
        repo = JsonRunRepository(tmp_path)
        first = make_run()
        repo.save(first)
        time.sleep(0.01)
        second = make_run()
        repo.save(second)

        result = repo.list_recent()

        assert [r.run_id for r in result] == [second.run_id, first.run_id]

    def test_respecte_la_limite(self, tmp_path):
        repo = JsonRunRepository(tmp_path)
        for _ in range(5):
            repo.save(make_run())
            time.sleep(0.001)

        assert len(repo.list_recent(limit=2)) == 2

    def test_fichier_illisible_est_ignore_sans_planter(self, tmp_path):
        (tmp_path / "corrompu.json").write_text("{ pas du json valide", encoding="utf-8")
        repo = JsonRunRepository(tmp_path)
        run = make_run()
        repo.save(run)

        result = repo.list_recent()

        assert [r.run_id for r in result] == [run.run_id]
