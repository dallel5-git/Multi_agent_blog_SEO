"""Entité `PipelineRun` : trace d'une exécution complète du pipeline.

C'est l'agrégat persistant du système : il porte l'identité d'un run, son état,
et sert de support à la validation humaine différée (Telegram).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class RunStatus(str, Enum):
    """Cycle de vie d'un run."""

    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"   # article prêt, en attente du bouton Telegram
    PUBLISHED = "published"               # ✅ confirmé → commit + push Git
    SAVED_LOCALLY = "saved_locally"       # ❌ refusé → .mdx écrit, push manuel par l'auteur
    DISCARDED = "discarded"
    FAILED = "failed"


class Decision(str, Enum):
    """Décision humaine reçue depuis Telegram."""

    APPROVE = "approve"   # ✅ Publier : écriture + commit + push
    REJECT = "reject"     # ❌ Garder en local : écriture seule
    REWRITE = "rewrite"   # 🔁 Relancer le Content Writer avec un feedback


@dataclass(slots=True)
class StepTrace:
    """Trace d'une étape (un agent) : durée, succès, message."""

    name: str
    started_at: datetime
    finished_at: datetime | None = None
    ok: bool = True
    detail: str = ""

    @property
    def duration_s(self) -> float:
        if self.finished_at is None:
            return 0.0
        return round((self.finished_at - self.started_at).total_seconds(), 2)


@dataclass(slots=True)
class PipelineRun:
    """Agrégat racine d'une exécution."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.RUNNING
    dry_run: bool = False
    steps: list[StepTrace] = field(default_factory=list)
    # Renseignés au fil du pipeline.
    topic_title: str = ""
    article_slug: str = ""
    draft_path: str = ""          # chemin du .mdx dans storage/drafts (toujours écrit)
    published_path: str = ""      # chemin final dans content/articles (si écrit)
    commit_sha: str = ""
    decision: Decision | None = None
    decided_at: datetime | None = None
    quality_score: float = 0.0
    revision_count: int = 1
    errors: list[str] = field(default_factory=list)

    def start_step(self, name: str) -> StepTrace:
        trace = StepTrace(name=name, started_at=datetime.now(UTC))
        self.steps.append(trace)
        return trace

    def end_step(self, trace: StepTrace, ok: bool = True, detail: str = "") -> None:
        trace.finished_at = datetime.now(UTC)
        trace.ok = ok
        trace.detail = detail
        if not ok:
            self.errors.append(f"{trace.name}: {detail}")

    def finish(self, status: RunStatus) -> None:
        self.status = status
        self.finished_at = datetime.now(UTC)

    @property
    def duration_s(self) -> float:
        end = self.finished_at or datetime.now(UTC)
        return round((end - self.started_at).total_seconds(), 2)

    def summary(self) -> str:
        return (
            f"run {self.run_id} — {self.status.value} — {self.duration_s}s — "
            f"{len(self.steps)} étapes — {len(self.errors)} erreur(s)"
        )
