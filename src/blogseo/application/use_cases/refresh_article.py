"""Cas d'usage : « régénération d'un article sous-performant » (issue #42).

Un article avec beaucoup d'impressions et peu de clics (voir
`PerformanceFeedback.underperforming_slugs`) a un problème de titre/description,
pas de fond : ce cas d'usage ne touche donc JAMAIS au corps de l'article ni à
son slug, seulement à `title`/`description` dans le frontmatter.

Le flux de validation reproduit celui d'un nouvel article (`PublisherAgent`) :
aperçu Telegram, ✅ Publier (mise à jour + push) / ❌ Garder en local /
🔁 Refaire une proposition. L'article existant n'est jamais modifié sans
cette validation humaine (sauf `HUMAN_REVIEW=false`, même dérogation que pour
un nouvel article).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from ...domain.entities.pipeline_run import Decision
from ...domain.errors import BlogSeoError
from ...domain.ports.analytics import AnalyticsPort, ArticlePerformance
from ...domain.ports.llm import LLMPort
from ...domain.ports.notifications import HumanReviewPort, NotifierPort
from ...domain.ports.publishing import ArticleRefreshPort, ExistingArticle, GitPublisherPort
from ...shared.json_utils import extract_json
from ...shared.seo_text import fix_meta_description, fix_meta_title
from ...shared.text import truncate
from ..prompts.refresh import REFRESH_SYSTEM, refresh_user_prompt

logger = logging.getLogger(__name__)

#: Nombre de propositions successives avant abandon (🔁 répété par l'auteur).
MAX_ATTEMPTS = 3


class ArticleNotFoundError(BlogSeoError):
    """Le slug demandé n'existe pas dans `content/articles/`."""


@dataclass(frozen=True, slots=True)
class RefreshResult:
    """Résultat d'un `blogseo refresh <slug>`."""

    slug: str
    decision: Decision | None
    old_title: str
    new_title: str
    old_description: str
    new_description: str
    path: Path | None = None
    commit_sha: str = ""

    @property
    def applied(self) -> bool:
        return self.path is not None


class RefreshArticleUseCase:
    """Régénère titre/description d'un article publié, avec validation humaine."""

    def __init__(
        self,
        llm: LLMPort,
        *,
        refresher: ArticleRefreshPort,
        analytics: AnalyticsPort,
        notifier: NotifierPort | None = None,
        reviewer: HumanReviewPort | None = None,
        human_review: bool = True,
        review_timeout_s: int = 86_400,
        default_on_timeout: Decision = Decision.REJECT,
        git: GitPublisherPort | None = None,
        commit_prefix: str = "content:",
        temperature: float = 0.4,
    ) -> None:
        self.llm = llm
        self.refresher = refresher
        self.analytics = analytics
        self.notifier = notifier
        self.reviewer = reviewer
        self.human_review = human_review
        self.review_timeout_s = review_timeout_s
        self.default_on_timeout = default_on_timeout
        self.git = git
        self.commit_prefix = commit_prefix
        self.temperature = temperature

    # ------------------------------------------------------------------ #
    def execute(self, slug: str) -> RefreshResult:
        existing = self.refresher.read(slug)
        if existing is None:
            raise ArticleNotFoundError(f"Aucun article publié avec le slug « {slug} »")

        performance = self._find_performance(slug)
        feedback = ""
        decision: Decision | None = None
        new_title, new_description = existing.title, existing.description

        for attempt in range(1, MAX_ATTEMPTS + 1):
            new_title, new_description = self._propose(existing, performance, feedback)
            decision = self._get_decision(
                slug, existing, new_title, new_description, attempt, performance
            )
            if decision is Decision.REWRITE and attempt < MAX_ATTEMPTS:
                feedback = (
                    "L'auteur a demandé une autre proposition : changez d'angle "
                    "(bénéfice différent, formulation différente), sans dénaturer le contenu."
                )
                continue
            break

        return self._apply(slug, existing, new_title, new_description, decision)

    # ------------------------------------------------------------------ #
    def _find_performance(self, slug: str) -> ArticlePerformance | None:
        performances = self.analytics.fetch_performance(days=28)
        return next((p for p in performances if p.slug == slug), None)

    def _propose(
        self, existing: ExistingArticle, performance: ArticlePerformance | None, feedback: str
    ) -> tuple[str, str]:
        top_queries = list(performance.top_queries) if performance else []
        focus_keyword = top_queries[0] if top_queries else ""

        response = self.llm.generate(
            REFRESH_SYSTEM,
            refresh_user_prompt(
                current_title=existing.title,
                current_description=existing.description,
                category=existing.category,
                article_excerpt=existing.body_markdown[:1500],
                focus_keyword=focus_keyword,
                top_queries=top_queries,
                impressions=performance.impressions if performance else 0,
                clicks=performance.clicks if performance else 0,
                ctr=performance.ctr if performance else 0.0,
                feedback=feedback,
            ),
            temperature=self.temperature,
            json_mode=True,
        )
        payload = extract_json(response.text, default={})

        title = fix_meta_title(str(payload.get("meta_title") or existing.title), focus_keyword)
        description = fix_meta_description(
            str(payload.get("meta_description") or existing.description),
            focus_keyword,
            existing.body_markdown,
        )
        return title, description

    def _get_decision(
        self,
        slug: str,
        existing: ExistingArticle,
        new_title: str,
        new_description: str,
        attempt: int,
        performance: ArticlePerformance | None,
    ) -> Decision:
        if not self.human_review:
            logger.warning("HUMAN_REVIEW=false : refresh de « %s » appliqué automatiquement", slug)
            return Decision.APPROVE
        if self.reviewer is None:
            logger.warning("Aucun canal de validation : repli sur l'écriture locale seule")
            return Decision.REJECT

        run_id = f"refresh-{uuid.uuid4().hex[:8]}"
        decision = self.reviewer.request_decision(
            run_id=run_id,
            title=new_title,
            preview=self._build_preview(slug, existing, new_title, new_description, attempt, performance),
            timeout_s=self.review_timeout_s,
        )
        if decision is None:
            logger.warning(
                "Délai de validation dépassé pour le refresh de « %s » : décision par défaut « %s »",
                slug, self.default_on_timeout.value,
            )
            return self.default_on_timeout
        return decision

    # ------------------------------------------------------------------ #
    def _apply(
        self,
        slug: str,
        existing: ExistingArticle,
        new_title: str,
        new_description: str,
        decision: Decision | None,
    ) -> RefreshResult:
        base = RefreshResult(
            slug=slug, decision=decision,
            old_title=existing.title, new_title=new_title,
            old_description=existing.description, new_description=new_description,
        )

        if decision is Decision.REWRITE:
            # Tentatives épuisées : rien n'est écrit, l'auteur relancera à la main.
            self._notify(
                f"⚠️ <b>Refresh abandonné</b> — <code>{slug}</code>\n"
                f"Aucune des {MAX_ATTEMPTS} propositions n'a été retenue. Rien n'a été modifié."
            )
            return base

        path = self.refresher.update_metadata(slug, title=new_title, description=new_description)
        result = replace(base, path=path)

        if decision is Decision.APPROVE:
            result = self._publish_to_git(slug, path, result)
        else:
            self._notify(
                f"💾 <b>Refresh enregistré en local</b> — <code>{slug}</code>\n"
                f"Relisez puis poussez vous-même."
            )
        return result

    def _publish_to_git(self, slug: str, path: Path, result: RefreshResult) -> RefreshResult:
        if self.git is None:
            self._notify(
                f"💾 <b>Refresh enregistré en local</b> — <code>{slug}</code>\n"
                f"⚠️ Dépôt Git non configuré : push impossible."
            )
            return result

        push = self.git.commit_and_push([path], f"{self.commit_prefix} refresh {slug}")
        result = replace(result, commit_sha=push.commit_sha)
        if push.pushed:
            self._notify(
                f"🚀 <b>Refresh publié</b> — <code>{slug}</code>\n"
                f"Commit <code>{push.commit_sha}</code> poussé sur {push.branch}."
            )
        else:
            self._notify(
                f"⚠️ <b>Push impossible</b>\n{self._escape(push.message)}\n\n"
                f"Le fichier est bien mis à jour dans <code>{path}</code>."
            )
        return result

    # ------------------------------------------------------------------ #
    def _build_preview(
        self,
        slug: str,
        existing: ExistingArticle,
        new_title: str,
        new_description: str,
        attempt: int,
        performance: ArticlePerformance | None,
    ) -> str:
        stats = (
            f"📊 {performance.impressions} impressions · {performance.clicks} clics · "
            f"CTR {performance.ctr:.2%}"
            if performance
            else "📊 (aucune donnée de performance disponible)"
        )
        lines = [
            f"♻️ <b>Refresh proposé</b> — <code>{slug}</code>"
            + (f" (essai {attempt}/{MAX_ATTEMPTS})" if attempt > 1 else ""),
            "",
            "<b>Titre actuel</b>",
            self._escape(existing.title),
            "<b>Nouveau titre</b>",
            f"<b>{self._escape(new_title)}</b>",
            "",
            "<b>Description actuelle</b>",
            self._escape(existing.description),
            "<b>Nouvelle description</b>",
            f"<i>{self._escape(new_description)}</i>",
            "",
            stats,
            "",
            "👇 Que faire ?",
            "✅ <b>Publier</b> — mise à jour + commit + push (Vercel déploie)",
            "❌ <b>Garder en local</b> — fichier mis à jour, vous pusherez vous-même",
            "🔁 <b>Refaire une proposition</b>",
        ]
        return truncate("\n".join(lines), 3900)

    def _notify(self, text: str) -> None:
        if self.notifier is not None:
            self.notifier.send(text)

    @staticmethod
    def _escape(text: str) -> str:
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
