"""Persistance des runs en JSON (un fichier par run) dans `storage/runs/`.

Suffisant pour un pipeline qui tourne une fois toutes les 48 h : pas de base de
données à installer, un fichier lisible à l'œil nu pour le débogage, et la
validation humaine différée survit à un redémarrage du process.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from ...domain.entities.pipeline_run import Decision, PipelineRun, RunStatus, StepTrace
from ...domain.ports.repositories import RunRepositoryPort

logger = logging.getLogger(__name__)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class JsonRunRepository(RunRepositoryPort):
    """Stockage fichier des `PipelineRun`."""

    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    # ------------------------------------------------------------------ #
    def save(self, run: PipelineRun) -> None:
        payload = {
            "run_id": run.run_id,
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
            "status": run.status.value,
            "dry_run": run.dry_run,
            "topic_title": run.topic_title,
            "article_slug": run.article_slug,
            "draft_path": run.draft_path,
            "published_path": run.published_path,
            "commit_sha": run.commit_sha,
            "decision": run.decision.value if run.decision else None,
            "decided_at": _iso(run.decided_at),
            "quality_score": run.quality_score,
            "revision_count": run.revision_count,
            "errors": run.errors,
            "steps": [
                {
                    "name": s.name,
                    "started_at": _iso(s.started_at),
                    "finished_at": _iso(s.finished_at),
                    "ok": s.ok,
                    "detail": s.detail,
                    "duration_s": s.duration_s,
                }
                for s in run.steps
            ],
        }
        try:
            self._path(run.run_id).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Impossible d'enregistrer le run %s : %s", run.run_id, exc)

    def get(self, run_id: str) -> PipelineRun | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.error("Run %s illisible : %s", run_id, exc)
            return None
        return self._to_entity(data)

    def list_awaiting_review(self) -> list[PipelineRun]:
        return [r for r in self._load_all() if r.status is RunStatus.AWAITING_REVIEW]

    def list_recent(self, limit: int = 20) -> list[PipelineRun]:
        runs = self._load_all()
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]

    # ------------------------------------------------------------------ #
    def _load_all(self) -> list[PipelineRun]:
        runs: list[PipelineRun] = []
        for path in self.runs_dir.glob("*.json"):
            try:
                runs.append(self._to_entity(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError) as exc:
                logger.debug("Run ignoré (%s) : %s", path.name, exc)
        return runs

    @staticmethod
    def _to_entity(data: dict) -> PipelineRun:
        run = PipelineRun(
            run_id=data["run_id"],
            started_at=_parse_dt(data.get("started_at")) or datetime.now(),
            finished_at=_parse_dt(data.get("finished_at")),
            status=RunStatus(data.get("status", "running")),
            dry_run=data.get("dry_run", False),
            topic_title=data.get("topic_title", ""),
            article_slug=data.get("article_slug", ""),
            draft_path=data.get("draft_path", ""),
            published_path=data.get("published_path", ""),
            commit_sha=data.get("commit_sha", ""),
            decision=Decision(data["decision"]) if data.get("decision") else None,
            decided_at=_parse_dt(data.get("decided_at")),
            quality_score=data.get("quality_score", 0.0),
            revision_count=data.get("revision_count", 1),
            errors=list(data.get("errors", [])),
        )
        run.steps = [
            StepTrace(
                name=s["name"],
                started_at=_parse_dt(s.get("started_at")) or run.started_at,
                finished_at=_parse_dt(s.get("finished_at")),
                ok=s.get("ok", True),
                detail=s.get("detail", ""),
            )
            for s in data.get("steps", [])
        ]
        return run
