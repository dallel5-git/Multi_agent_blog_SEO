"""Tests du maillage retour de série lors de la publication (issue #41).

Critère d'acceptation vérifié : chaque article de la série lie les précédents
(déjà couvert par `test_seo_editor` / le « À lire aussi ») et est lié par les
suivants — ce qui suppose de rouvrir les `.mdx` déjà publiés, uniquement quand
un push Git réel a effectivement lieu (jamais en dry-run ou en REJECT).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from blogseo.application.agents.publisher import PublisherAgent
from blogseo.application.dto.pipeline_state import PipelineState
from blogseo.domain.entities.pipeline_run import Decision, PipelineRun, RunStatus
from blogseo.domain.entities.series import ArticleSeries, SeriesTopic
from blogseo.domain.ports.notifications import HumanReviewPort, NotifierPort
from blogseo.domain.ports.publishing import GitPublisherPort, PushResult
from blogseo.domain.ports.repositories import SeriesRepositoryPort
from blogseo.domain.value_objects.category import Category
from blogseo.infrastructure.publishing.mdx_writer import MdxArticleWriter
from blogseo.infrastructure.publishing.series_linker import SeriesBacklinkWriter


class SpyReviewer(NotifierPort, HumanReviewPort):
    name = "spy"

    def __init__(self, decision: Decision | None) -> None:
        self.decision = decision
        self.messages: list[str] = []

    def send(self, text: str, *, silent: bool = False) -> bool:
        self.messages.append(text)
        return True

    def send_document(self, path, caption: str = "") -> bool:
        return True

    def request_decision(self, *, run_id, title, preview, document=None, timeout_s=0):
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


class InMemorySeriesRepository(SeriesRepositoryPort):
    def __init__(self, series: ArticleSeries) -> None:
        self._series = series
        self.saved: list[ArticleSeries] = []

    def save(self, series: ArticleSeries) -> None:
        self._series = series
        self.saved.append(series)

    def get(self, series_id: str) -> ArticleSeries | None:
        return self._series if self._series.series_id == series_id else None

    def find_active(self) -> ArticleSeries | None:
        return self._series if self._series.is_active else None

    def list_all(self) -> list[ArticleSeries]:
        return [self._series]


@pytest.fixture
def dirs(tmp_path):
    drafts = tmp_path / "drafts"
    blog = tmp_path / "blog" / "content" / "articles"
    drafts.mkdir(parents=True)
    blog.mkdir(parents=True)
    return drafts, blog


def make_series() -> ArticleSeries:
    return ArticleSeries(
        theme="n8n",
        title="Automatiser sa PME avec n8n",
        topics=[
            SeriesTopic(
                title="Découverte de n8n", angle="angle", category=Category.N8N,
                primary_keyword="n8n", status="published", slug="decouverte-n8n",
            ),
            SeriesTopic(
                title="Automatiser sa prospection avec n8n", angle="angle", category=Category.N8N,
                primary_keyword="prospection n8n", status="pending",
            ),
        ],
    )


def write_existing_episode(blog_dir: Path) -> None:
    (blog_dir / "decouverte-n8n.mdx").write_text(
        "---\ntitle: \"Découverte de n8n\"\n---\n\nContenu du premier épisode.\n",
        encoding="utf-8",
    )


def build_publisher(dirs, *, decision, git, series_repo):
    drafts, blog = dirs
    reviewer = SpyReviewer(decision)
    return PublisherAgent(
        MdxArticleWriter(drafts),
        drafts_dir=drafts,
        blog_content_dir=blog,
        git=git,
        image_generator=None,
        cover_output_dir=None,
        notifier=reviewer,
        reviewer=reviewer,
        human_review=True,
        review_timeout_s=1,
        default_on_timeout=Decision.REJECT,
        series_repository=series_repo,
        series_linker=SeriesBacklinkWriter(blog),
    )


def build_state(article, *, series: ArticleSeries, dry_run: bool = False) -> PipelineState:
    state = PipelineState(run=PipelineRun(dry_run=dry_run))
    state.article = article
    state.series_id = series.series_id
    state.series_topic_index = 1
    return state


class TestMaillageRetourALaPublication:
    def test_publication_relie_l_episode_precedent_et_est_marquee_publiee(self, dirs, article):
        _, blog = dirs
        write_existing_episode(blog)
        series = make_series()
        repo = InMemorySeriesRepository(series)
        git = SpyGit(pushed=True)
        agent = build_publisher(dirs, decision=Decision.APPROVE, git=git, series_repo=repo)

        state = agent.run(build_state(article, series=series))

        assert state.run.status is RunStatus.PUBLISHED
        assert series.topics[1].status == "published"
        assert series.topics[1].slug == article.slug.value

        old_content = (blog / "decouverte-n8n.mdx").read_text(encoding="utf-8")
        assert "## Cette série" in old_content
        assert f"/blog/{article.slug.value}" in old_content
        assert "/blog/decouverte-n8n" not in old_content  # pas de lien vers soi-même

        new_content = (blog / f"{article.slug.value}.mdx").read_text(encoding="utf-8")
        assert "/blog/decouverte-n8n" in new_content

        committed_paths = {p.name for p in git.calls[0][0]}
        assert "decouverte-n8n.mdx" in committed_paths
        assert f"{article.slug.value}.mdx" in committed_paths

    def test_rejoue_sans_effet_si_le_push_echoue(self, dirs, article):
        """Si le push échoue, le sujet reste marqué « publié » (simplification assumée :
        le commit local existe déjà, un push manuel ultérieur suffit à tout aligner)."""
        _, blog = dirs
        write_existing_episode(blog)
        series = make_series()
        repo = InMemorySeriesRepository(series)
        agent = build_publisher(dirs, decision=Decision.APPROVE, git=SpyGit(pushed=False), series_repo=repo)

        state = agent.run(build_state(article, series=series))

        assert state.run.status is RunStatus.SAVED_LOCALLY
        assert series.topics[1].status == "published"


class TestDecisionRejeteeNeDeclenchePasLeMaillage:
    def test_ecrit_le_sujet_comme_written_sans_toucher_aux_episodes(self, dirs, article):
        _, blog = dirs
        write_existing_episode(blog)
        series = make_series()
        repo = InMemorySeriesRepository(series)
        git = SpyGit()
        agent = build_publisher(dirs, decision=Decision.REJECT, git=git, series_repo=repo)

        state = agent.run(build_state(article, series=series))

        assert state.run.status is RunStatus.SAVED_LOCALLY
        assert git.calls == []
        assert series.topics[1].status == "written"
        assert series.topics[1].slug == article.slug.value

        old_content = (blog / "decouverte-n8n.mdx").read_text(encoding="utf-8")
        assert "## Cette série" not in old_content


class TestDryRunNeConsommePasLaFile:
    def test_le_sujet_reste_en_attente(self, dirs, article):
        series = make_series()
        repo = InMemorySeriesRepository(series)
        agent = build_publisher(dirs, decision=Decision.APPROVE, git=SpyGit(), series_repo=repo)

        state = agent.run(build_state(article, series=series, dry_run=True))

        assert state.run.status is RunStatus.SAVED_LOCALLY
        assert series.topics[1].status == "pending"
        assert not repo.saved
