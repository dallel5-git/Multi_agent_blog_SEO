"""Tests de `RefreshArticleUseCase` (issue #42) : règle métier centrale —

    ✅ APPROVE → mise à jour du fichier + commit + push
    ❌ REJECT  → mise à jour du fichier SEULEMENT (push manuel)
    🔁 REWRITE → nouvelle proposition ; après 3 essais, RIEN n'est écrit

Le corps de l'article et son slug ne sont jamais transmis à l'écriture :
seuls `title`/`description` passent par `ArticleRefreshPort.update_metadata`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blogseo.application.use_cases.refresh_article import (
    MAX_ATTEMPTS,
    ArticleNotFoundError,
    RefreshArticleUseCase,
)
from blogseo.domain.entities.pipeline_run import Decision
from blogseo.domain.ports.analytics import AnalyticsPort, ArticlePerformance
from blogseo.domain.ports.llm import LLMPort, LLMResponse
from blogseo.domain.ports.notifications import HumanReviewPort, NotifierPort
from blogseo.domain.ports.publishing import (
    ArticleRefreshPort,
    ExistingArticle,
    GitPublisherPort,
    PushResult,
)

EXISTING = ExistingArticle(
    slug="automatiser-prospection-n8n",
    title="Automatiser sa prospection avec n8n",
    description="Ancienne description, peu incitative.",
    category="n8n",
    body_markdown="## Introduction\n\nContenu existant de l'article, inchangé par le refresh.\n",
)

NEW_PAYLOAD = {
    "meta_title": "Automatiser sa prospection avec n8n : guide 2026",
    "meta_description": "Nouvelle description bien plus incitative au clic, avec le mot-clé n8n dedans.",
}


class StubLLM(LLMPort):
    name = "stub"

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.calls: list[str] = []

    def generate(self, system_prompt, user_prompt, *, temperature=0.7, max_output_tokens=4096, json_mode=False):
        self.calls.append(user_prompt)
        index = min(len(self.calls) - 1, len(self.payloads) - 1)
        return LLMResponse(text=json.dumps(self.payloads[index]), provider=self.name, model="stub")

    def is_available(self) -> bool:
        return True


class FakeRefresher(ArticleRefreshPort):
    def __init__(self, existing: ExistingArticle | None) -> None:
        self._existing = existing
        self.updates: list[tuple[str, str, str]] = []

    def read(self, slug: str) -> ExistingArticle | None:
        return self._existing if self._existing and slug == self._existing.slug else None

    def update_metadata(self, slug: str, *, title: str, description: str) -> Path | None:
        if not self._existing or slug != self._existing.slug:
            return None
        self.updates.append((slug, title, description))
        return Path(f"/fake/blog/{slug}.mdx")


class FakeAnalytics(AnalyticsPort):
    name = "fake-analytics"

    def __init__(self, performances: list[ArticlePerformance] | None = None) -> None:
        self._performances = performances or []

    def fetch_performance(self, *, days: int = 28) -> list[ArticlePerformance]:
        return self._performances


class SpyReviewer(NotifierPort, HumanReviewPort):
    name = "spy"

    def __init__(self, decisions: list[Decision | None]) -> None:
        self.decisions = decisions
        self.messages: list[str] = []
        self.previews: list[str] = []

    def send(self, text: str, *, silent: bool = False) -> bool:
        self.messages.append(text)
        return True

    def send_document(self, path: Path, caption: str = "") -> bool:
        return True

    def request_decision(self, *, run_id, title, preview, document=None, timeout_s=0):
        self.previews.append(preview)
        index = min(len(self.previews) - 1, len(self.decisions) - 1)
        return self.decisions[index]

    def acknowledge(self, run_id, decision, detail="") -> None:
        pass


class SpyGit(GitPublisherPort):
    def __init__(self, *, pushed: bool = True) -> None:
        self.pushed = pushed
        self.calls: list[tuple[list[Path], str]] = []

    def is_clean(self) -> bool:
        return True

    def commit_and_push(self, paths, message) -> PushResult:
        self.calls.append((list(paths), message))
        return PushResult(committed=True, pushed=self.pushed, commit_sha="abc1234",
                          branch="main", message="ok" if self.pushed else "push refusé")


def build_use_case(*, decisions, refresher=None, analytics=None, git=None, human_review=True):
    reviewer = SpyReviewer(decisions)
    use_case = RefreshArticleUseCase(
        StubLLM([NEW_PAYLOAD]),
        refresher=refresher or FakeRefresher(EXISTING),
        analytics=analytics or FakeAnalytics(),
        notifier=reviewer,
        reviewer=reviewer,
        human_review=human_review,
        review_timeout_s=1,
        default_on_timeout=Decision.REJECT,
        git=git,
    )
    return use_case, reviewer


class TestSlugIntrouvable:
    def test_leve_une_erreur_explicite(self):
        use_case, _ = build_use_case(decisions=[Decision.APPROVE], refresher=FakeRefresher(None))
        with pytest.raises(ArticleNotFoundError):
            use_case.execute("slug-inconnu")


class TestDecisionApprouve:
    def test_met_a_jour_le_fichier_et_pousse(self):
        refresher = FakeRefresher(EXISTING)
        git = SpyGit(pushed=True)
        use_case, spy = build_use_case(decisions=[Decision.APPROVE], refresher=refresher, git=git)

        result = use_case.execute(EXISTING.slug)

        assert result.applied
        assert result.decision is Decision.APPROVE
        assert result.old_title == EXISTING.title
        assert result.new_title == NEW_PAYLOAD["meta_title"]
        assert refresher.updates == [(EXISTING.slug, result.new_title, result.new_description)]
        assert len(git.calls) == 1
        assert f"refresh {EXISTING.slug}" in git.calls[0][1]
        assert result.commit_sha == "abc1234"
        assert any("publié" in m.lower() for m in spy.messages)

    def test_sans_depot_git_le_fichier_est_quand_meme_mis_a_jour(self):
        refresher = FakeRefresher(EXISTING)
        use_case, spy = build_use_case(decisions=[Decision.APPROVE], refresher=refresher, git=None)

        result = use_case.execute(EXISTING.slug)

        assert result.applied
        assert result.commit_sha == ""
        assert any("Git" in m for m in spy.messages)


class TestDecisionRefuse:
    def test_met_a_jour_le_fichier_mais_ne_pousse_pas(self):
        refresher = FakeRefresher(EXISTING)
        git = SpyGit()
        use_case, spy = build_use_case(decisions=[Decision.REJECT], refresher=refresher, git=git)

        result = use_case.execute(EXISTING.slug)

        assert result.applied
        assert git.calls == []
        assert any("local" in m.lower() for m in spy.messages)

    def test_seuls_titre_et_description_sont_transmis_a_l_ecriture(self):
        refresher = FakeRefresher(EXISTING)
        use_case, _ = build_use_case(decisions=[Decision.REJECT], refresher=refresher)

        use_case.execute(EXISTING.slug)

        slug, title, description = refresher.updates[0]
        assert slug == EXISTING.slug  # jamais de changement de slug
        assert title == NEW_PAYLOAD["meta_title"]
        assert description.startswith("Nouvelle description")


class TestDecisionReecrire:
    def test_boucle_puis_applique_la_decision_finale(self):
        refresher = FakeRefresher(EXISTING)
        use_case, spy = build_use_case(
            decisions=[Decision.REWRITE, Decision.REWRITE, Decision.APPROVE], refresher=refresher
        )

        result = use_case.execute(EXISTING.slug)

        assert len(spy.previews) == 3
        assert result.decision is Decision.APPROVE
        assert result.applied

    def test_abandon_apres_le_nombre_max_de_tentatives_ne_touche_rien(self):
        refresher = FakeRefresher(EXISTING)
        use_case, spy = build_use_case(
            decisions=[Decision.REWRITE] * MAX_ATTEMPTS, refresher=refresher
        )

        result = use_case.execute(EXISTING.slug)

        assert len(spy.previews) == MAX_ATTEMPTS
        assert result.decision is Decision.REWRITE
        assert not result.applied
        assert refresher.updates == []
        assert any("abandonné" in m.lower() for m in spy.messages)


class TestExpirationDuDelai:
    def test_aucune_reponse_applique_la_decision_par_defaut(self):
        refresher = FakeRefresher(EXISTING)
        git = SpyGit()
        use_case, _ = build_use_case(decisions=[None], refresher=refresher, git=git)

        result = use_case.execute(EXISTING.slug)

        assert result.applied  # REJECT = écriture locale seule
        assert git.calls == []


class TestSansValidationHumaine:
    def test_human_review_false_applique_directement(self):
        refresher = FakeRefresher(EXISTING)
        git = SpyGit()
        use_case, spy = build_use_case(
            decisions=[None], refresher=refresher, git=git, human_review=False
        )

        result = use_case.execute(EXISTING.slug)

        assert spy.previews == []
        assert len(git.calls) == 1
        assert result.decision is Decision.APPROVE


class TestSansDonneesDePerformance:
    def test_fonctionne_sans_export_search_console(self):
        refresher = FakeRefresher(EXISTING)
        use_case, spy = build_use_case(
            decisions=[Decision.REJECT], refresher=refresher, analytics=FakeAnalytics([])
        )

        result = use_case.execute(EXISTING.slug)

        assert result.applied
        assert "aucune donnée de performance" in spy.previews[0].lower()


class TestApercuTelegram:
    def test_contient_le_titre_et_la_description_avant_apres(self):
        refresher = FakeRefresher(EXISTING)
        performances = [ArticlePerformance(
            slug=EXISTING.slug, impressions=500, clicks=2, average_position=8.0,
            top_queries=("automatiser prospection n8n",),
        )]
        use_case, spy = build_use_case(
            decisions=[Decision.REJECT], refresher=refresher, analytics=FakeAnalytics(performances)
        )

        use_case.execute(EXISTING.slug)

        preview = spy.previews[0]
        assert EXISTING.title in preview
        assert NEW_PAYLOAD["meta_title"] in preview
        assert "500 impressions" in preview
        assert "Publier" in preview and "Garder en local" in preview and "Refaire" in preview
        assert len(preview) <= 4000
