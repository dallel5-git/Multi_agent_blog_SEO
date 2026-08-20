"""Tests de la règle métier centrale du Publisher.

    ✅ APPROVE → écriture dans content/articles/ + commit + push
    ❌ REJECT  → écriture dans content/articles/ SEULEMENT (push manuel)
    🔁 REWRITE → retour au Content Writer, rien n'est écrit dans le blog
    dry-run    → brouillon seul, aucune écriture dans le blog
"""

from __future__ import annotations

from pathlib import Path

import pytest

from blogseo.application.agents.publisher import PublisherAgent
from blogseo.application.dto.pipeline_state import PipelineState
from blogseo.domain.entities.pipeline_run import Decision, PipelineRun, RunStatus
from blogseo.domain.ports.notifications import HumanReviewPort, NotifierPort
from blogseo.domain.ports.publishing import GitPublisherPort, PushResult
from blogseo.infrastructure.publishing.mdx_writer import MdxArticleWriter


class SpyReviewer(NotifierPort, HumanReviewPort):
    name = "spy"

    def __init__(self, decision: Decision | None) -> None:
        self.decision = decision
        self.messages: list[str] = []
        self.previews: list[str] = []

    def send(self, text: str, *, silent: bool = False) -> bool:
        self.messages.append(text)
        return True

    def send_document(self, path: Path, caption: str = "") -> bool:
        return True

    def request_decision(self, *, run_id, title, preview, document=None, timeout_s=0):
        self.previews.append(preview)
        return self.decision

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


@pytest.fixture
def dirs(tmp_path):
    drafts = tmp_path / "drafts"
    blog = tmp_path / "blog" / "content" / "articles"
    drafts.mkdir(parents=True)
    blog.mkdir(parents=True)
    return drafts, blog


def build_publisher(dirs, *, decision, git=None, human_review=True, reviewer=None):
    drafts, blog = dirs
    reviewer = reviewer or SpyReviewer(decision)
    agent = PublisherAgent(
        MdxArticleWriter(drafts),
        drafts_dir=drafts,
        blog_content_dir=blog,
        git=git,
        image_generator=None,
        cover_output_dir=None,
        notifier=reviewer,
        reviewer=reviewer,
        human_review=human_review,
        review_timeout_s=1,
        default_on_timeout=Decision.REJECT,
    )
    return agent, reviewer


def build_state(article, *, dry_run=False) -> PipelineState:
    state = PipelineState(run=PipelineRun(dry_run=dry_run))
    state.article = article
    state.iteration = 1
    return state


class TestDecisionApprouve:
    def test_ecrit_dans_le_blog_et_pousse(self, dirs, article):
        drafts, blog = dirs
        git = SpyGit(pushed=True)
        agent, _ = build_publisher(dirs, decision=Decision.APPROVE, git=git)

        state = agent.run(build_state(article))

        assert (blog / "automatiser-prospection-n8n.mdx").exists()
        assert state.run.status is RunStatus.PUBLISHED
        assert state.commit_sha == "abc1234"
        assert len(git.calls) == 1
        assert "content:" in git.calls[0][1]

    def test_statut_local_si_le_push_echoue(self, dirs, article):
        _, blog = dirs
        agent, spy = build_publisher(dirs, decision=Decision.APPROVE, git=SpyGit(pushed=False))

        state = agent.run(build_state(article))

        # Le fichier est écrit malgré tout : le travail n'est jamais perdu.
        assert (blog / "automatiser-prospection-n8n.mdx").exists()
        assert state.run.status is RunStatus.SAVED_LOCALLY
        assert any("Push impossible" in m for m in spy.messages)

    def test_avertit_si_aucun_depot_git(self, dirs, article):
        agent, spy = build_publisher(dirs, decision=Decision.APPROVE, git=None)
        state = agent.run(build_state(article))
        assert state.run.status is RunStatus.SAVED_LOCALLY
        assert any("Git" in w for w in state.warnings)


class TestDecisionRefuse:
    def test_ecrit_le_fichier_mais_ne_pousse_pas(self, dirs, article):
        _, blog = dirs
        git = SpyGit()
        agent, spy = build_publisher(dirs, decision=Decision.REJECT, git=git)

        state = agent.run(build_state(article))

        assert (blog / "automatiser-prospection-n8n.mdx").exists()
        assert git.calls == []           # AUCUN commit, AUCUN push
        assert state.run.status is RunStatus.SAVED_LOCALLY
        assert any("git push" in m for m in spy.messages)

    def test_le_fichier_ecrit_est_valide(self, dirs, article):
        _, blog = dirs
        agent, _ = build_publisher(dirs, decision=Decision.REJECT, git=SpyGit())
        agent.run(build_state(article))

        contenu = (blog / "automatiser-prospection-n8n.mdx").read_text(encoding="utf-8")
        assert contenu.startswith("---")
        assert 'category: "n8n"' in contenu
        assert contenu.count("---") >= 2


class TestDecisionReecrire:
    def test_ne_touche_pas_au_blog_et_arme_la_revision(self, dirs, article):
        _, blog = dirs
        git = SpyGit()
        agent, _ = build_publisher(dirs, decision=Decision.REWRITE, git=git)

        state = agent.run(build_state(article))

        assert list(blog.glob("*.mdx")) == []
        assert git.calls == []
        assert state.revision_instructions
        assert state.run.decision is Decision.REWRITE


class TestDryRun:
    def test_ecrit_seulement_le_brouillon(self, dirs, article):
        drafts, blog = dirs
        git = SpyGit()
        agent, _ = build_publisher(dirs, decision=Decision.APPROVE, git=git)

        state = agent.run(build_state(article, dry_run=True))

        assert (drafts / "automatiser-prospection-n8n.mdx").exists()
        assert list(blog.glob("*.mdx")) == []
        assert git.calls == []
        assert state.run.status is RunStatus.SAVED_LOCALLY


class TestExpirationDuDelai:
    def test_aucune_reponse_applique_la_decision_par_defaut(self, dirs, article):
        _, blog = dirs
        git = SpyGit()
        agent, _ = build_publisher(dirs, decision=None, git=git)  # None = pas de réponse

        state = agent.run(build_state(article))

        assert (blog / "automatiser-prospection-n8n.mdx").exists()
        assert git.calls == []  # par défaut on NE publie PAS
        assert state.run.status is RunStatus.SAVED_LOCALLY


class TestSansValidationHumaine:
    def test_human_review_false_publie_directement(self, dirs, article):
        git = SpyGit()
        agent, spy = build_publisher(dirs, decision=None, git=git, human_review=False)

        state = agent.run(build_state(article))

        assert spy.previews == []  # aucune demande de validation
        assert len(git.calls) == 1
        assert state.run.status is RunStatus.PUBLISHED


class TestApercuTelegram:
    def test_l_apercu_contient_les_informations_cles(self, dirs, article):
        agent, spy = build_publisher(dirs, decision=Decision.REJECT, git=SpyGit())
        agent.run(build_state(article))

        preview = spy.previews[0]
        assert article.seo.meta_title in preview
        assert "automatiser-prospection-n8n" in preview
        assert "Publier" in preview and "Garder en local" in preview
        assert len(preview) <= 4000  # limite de l'API Telegram
