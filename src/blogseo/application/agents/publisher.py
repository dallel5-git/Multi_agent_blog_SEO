"""Agent 8/9 — Publisher : couverture, validation humaine et publication.

C'est ici que se joue la règle métier définie par l'auteur :

    ✅ « Publier »        → écriture dans content/articles/ + git commit + push
                            → Vercel déploie automatiquement.
    ❌ « Garder en local » → écriture dans content/articles/ SEULEMENT.
                            L'auteur relit puis fait `git push` lui-même.
    🔁 « Faire réécrire »  → retour au Content Writer avec un feedback.

En `--dry-run`, rien n'est écrit dans le blog : seul le brouillon
`storage/drafts/` est produit et affiché.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ...domain.entities.pipeline_run import Decision, RunStatus
from ...domain.errors import PublicationError
from ...domain.ports.notifications import HumanReviewPort, NotifierPort
from ...domain.ports.publishing import ArticleWriterPort, GitPublisherPort, ImageGeneratorPort
from ...shared.text import truncate
from ..dto.pipeline_state import PipelineState
from ..prompts.reviewing import cover_image_prompt
from .base import Agent


class PublisherAgent(Agent):
    """Génération de couverture, validation humaine, écriture et publication Git."""

    name = "publisher"
    label = "Publisher — validation et publication"
    critical = True

    def __init__(
        self,
        writer: ArticleWriterPort,
        *,
        drafts_dir: Path,
        blog_content_dir: Path,
        git: GitPublisherPort | None = None,
        image_generator: ImageGeneratorPort | None = None,
        cover_output_dir: Path | None = None,
        cover_url_prefix: str = "/covers",
        notifier: NotifierPort | None = None,
        reviewer: HumanReviewPort | None = None,
        human_review: bool = True,
        review_timeout_s: int = 86_400,
        default_on_timeout: Decision = Decision.REJECT,
        commit_prefix: str = "content:",
        blog_url: str = "",
    ) -> None:
        super().__init__()
        self.writer = writer
        self.drafts_dir = drafts_dir
        self.blog_content_dir = blog_content_dir
        self.git = git
        self.image_generator = image_generator
        self.cover_output_dir = cover_output_dir
        self.cover_url_prefix = cover_url_prefix
        self.notifier = notifier
        self.reviewer = reviewer
        self.human_review = human_review
        self.review_timeout_s = review_timeout_s
        self.default_on_timeout = default_on_timeout
        self.commit_prefix = commit_prefix
        self.blog_url = blog_url.rstrip("/")

    # ------------------------------------------------------------------ #
    def run(self, state: PipelineState) -> PipelineState:
        article = state.article
        if article is None:
            raise PublicationError("Aucun article à publier")

        # 1. Image de couverture (jamais bloquant).
        self._generate_cover(state)

        # 2. Brouillon systématique — même en dry-run, même si tout le reste échoue.
        draft = self.writer.write(article, destination=self.drafts_dir, overwrite=True)
        state.draft_path = str(draft.path)
        state.run.draft_path = str(draft.path)
        self.logger.info("Brouillon enregistré : %s", draft.path)

        # 3. Mode dry-run : on s'arrête là.
        if state.run.dry_run:
            self.logger.info("Mode --dry-run : aucune écriture dans le blog, aucun push Git")
            state.run.finish(RunStatus.SAVED_LOCALLY)
            self._notify_dry_run(state)
            return state

        # 4. Décision : humaine via Telegram, ou automatique si HUMAN_REVIEW=false.
        decision = self._get_decision(state)
        state.run.decision = decision

        if decision is Decision.REWRITE:
            state.revision_instructions = (
                "L'auteur a demandé une réécriture depuis Telegram. Retravaillez l'article en "
                "profondeur : renforcez l'angle tunisien, ajoutez des exemples chiffrés concrets "
                "et rendez les explications plus opérationnelles."
            )
            self.logger.info("Réécriture demandée : retour au Content Writer")
            return state

        # 5. Écriture dans le blog — commune aux décisions ✅ et ❌.
        published = self.writer.write(article, destination=self.blog_content_dir, overwrite=False)
        state.published_path = str(published.path)
        state.run.published_path = str(published.path)
        self.logger.info("Article écrit dans le blog : %s", published.path)

        paths_to_commit = [published.path]
        cover_target = self._copy_cover_to_blog(state)
        if cover_target is not None:
            paths_to_commit.append(cover_target)

        # 6. Push Git uniquement si l'auteur a confirmé.
        if decision is Decision.APPROVE:
            self._publish_to_git(state, paths_to_commit)
        else:
            state.run.finish(RunStatus.SAVED_LOCALLY)
            self._notify_local_save(state)

        return state

    # ------------------------------------------------------------------ #
    # Étapes internes
    # ------------------------------------------------------------------ #
    def _generate_cover(self, state: PipelineState) -> None:
        article = state.article
        if self.image_generator is None:
            self.logger.info("Génération d'image désactivée")
            return
        try:
            prompt = cover_image_prompt(article.title, article.category.value)
            path = self.image_generator.generate(prompt, slug=article.slug.value)
        except Exception as exc:  # noqa: BLE001 - jamais bloquant
            self.logger.warning("Génération de couverture en échec : %s", exc)
            return

        if path is None:
            state.warn("Aucune image de couverture générée")
            return
        state.cover_path = str(path)
        article.cover_image = f"{self.cover_url_prefix}/{path.name}"
        self.logger.info("Couverture : %s → %s", path.name, article.cover_image)

    def _copy_cover_to_blog(self, state: PipelineState) -> Path | None:
        """Copie l'image générée dans `public/covers` du blog Next.js."""
        if not state.cover_path or self.cover_output_dir is None:
            return None
        source = Path(state.cover_path)
        if not source.exists():
            return None
        try:
            self.cover_output_dir.mkdir(parents=True, exist_ok=True)
            target = self.cover_output_dir / source.name
            shutil.copy2(source, target)
            self.logger.info("Couverture copiée dans le blog : %s", target)
            return target
        except OSError as exc:
            self.logger.warning("Copie de la couverture impossible : %s", exc)
            state.warn(f"Couverture non copiée : {exc}")
            return None

    def _get_decision(self, state: PipelineState) -> Decision:
        """Demande la décision humaine, ou applique le mode automatique."""
        if not self.human_review:
            self.logger.warning(
                "HUMAN_REVIEW=false : publication automatique sans validation humaine"
            )
            return Decision.APPROVE

        if self.reviewer is None:
            self.logger.warning("Aucun canal de validation : repli sur l'écriture locale seule")
            return Decision.REJECT

        state.run.status = RunStatus.AWAITING_REVIEW
        decision = self.reviewer.request_decision(
            run_id=state.run.run_id,
            title=state.article.title,
            preview=self._build_preview(state),
            document=Path(state.draft_path) if state.draft_path else None,
            timeout_s=self.review_timeout_s,
        )
        if decision is None:
            self.logger.warning(
                "Délai de validation dépassé : application de la décision par défaut « %s »",
                self.default_on_timeout.value,
            )
            return self.default_on_timeout
        return decision

    def _publish_to_git(self, state: PipelineState, paths: list[Path]) -> None:
        if self.git is None:
            state.warn("Publication Git demandée mais aucun dépôt configuré")
            state.run.finish(RunStatus.SAVED_LOCALLY)
            self._notify_local_save(state, extra="⚠️ Dépôt Git non configuré : push impossible.")
            return

        message = f"{self.commit_prefix} {state.article.seo.meta_title}".strip()
        result = self.git.commit_and_push(paths, message)
        state.commit_sha = result.commit_sha
        state.run.commit_sha = result.commit_sha

        if result.pushed:
            state.run.finish(RunStatus.PUBLISHED)
            url = f"{self.blog_url}/blog/{state.article.slug}" if self.blog_url else ""
            self._notify(
                f"🚀 <b>Article publié</b>\n"
                f"<b>{self._escape(state.article.seo.meta_title)}</b>\n"
                f"Commit <code>{result.commit_sha}</code> poussé sur {result.branch}.\n"
                f"Vercel déploie dans une minute."
                + (f"\n\n🔗 {url}" if url else "")
            )
        else:
            state.run.finish(RunStatus.SAVED_LOCALLY)
            state.warn(result.message)
            self._notify(
                f"⚠️ <b>Push impossible</b>\n{self._escape(result.message)}\n\n"
                f"Le fichier est bien écrit dans <code>{state.published_path}</code>."
            )

    # ------------------------------------------------------------------ #
    # Notifications
    # ------------------------------------------------------------------ #
    def _build_preview(self, state: PipelineState) -> str:
        """Aperçu HTML envoyé sur Telegram avec les boutons de décision."""
        article = state.article
        quality = state.quality
        topic = state.topic
        excerpt = truncate(
            " ".join(
                line for line in article.body_markdown.splitlines()
                if line.strip() and not line.strip().startswith(("#", "`", "<", "-"))
            ),
            600,
        )
        quality_line = (
            f"📊 {article.word_count} mots · {article.h2_count} sections · "
            f"qualité {quality.score:.0%}"
            if quality
            else f"📊 {article.word_count} mots · {article.h2_count} sections"
        )
        warnings = ""
        if quality and quality.warnings:
            warnings = "\n⚠️ " + "\n⚠️ ".join(
                self._escape(c.message) for c in quality.warnings[:3]
            )

        lines = [
            f"📝 <b>Nouvel article prêt</b> — run <code>{state.run.run_id}</code>",
            "",
            f"<b>{self._escape(article.seo.meta_title)}</b>",
            f"<i>{self._escape(article.seo.meta_description)}</i>",
            "",
            f"📂 Catégorie : {self._escape(article.category.value)}",
            f"🔑 Mot-clé : {self._escape(article.seo.focus_keyword)}",
            f"🔗 Slug : <code>{article.slug}</code>",
            quality_line,
            f"🇹🇳 Angle : {self._escape(truncate(topic.angle if topic else '', 200))}",
            warnings,
            "",
            "<b>Extrait</b>",
            self._escape(excerpt),
            "",
            "👇 Que faire ?",
            "✅ <b>Publier</b> — écriture + commit + push (Vercel déploie)",
            "❌ <b>Garder en local</b> — fichier écrit, vous pusherez vous-même",
            "🔁 <b>Faire réécrire</b> — retour au rédacteur",
        ]
        return truncate("\n".join(line for line in lines if line is not None), 3900)

    def _notify(self, text: str) -> None:
        if self.notifier is not None:
            self.notifier.send(text)

    def _notify_local_save(self, state: PipelineState, extra: str = "") -> None:
        self._notify(
            f"💾 <b>Article enregistré en local</b>\n"
            f"<code>{state.published_path}</code>\n\n"
            f"Relisez-le puis poussez avec :\n"
            f"<code>git add . &amp;&amp; git commit -m \"content: {self._escape(state.article.seo.meta_title)}\" "
            f"&amp;&amp; git push</code>"
            + (f"\n\n{extra}" if extra else "")
        )

    def _notify_dry_run(self, state: PipelineState) -> None:
        self._notify(
            f"🧪 <b>Dry-run terminé</b> — run <code>{state.run.run_id}</code>\n"
            f"<b>{self._escape(state.article.seo.meta_title)}</b>\n"
            f"{state.article.word_count} mots — brouillon : <code>{state.draft_path}</code>\n"
            f"Aucune écriture dans le blog, aucun push."
        )

    @staticmethod
    def _escape(text: str) -> str:
        """Échappe le HTML pour l'API Telegram (parse_mode=HTML)."""
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def describe(self, state: PipelineState) -> str:
        return f"{state.run.status.value} — {state.published_path or state.draft_path}"
