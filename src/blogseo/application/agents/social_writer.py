"""Agent 10/10 — Social Writer : post LinkedIn + thread X depuis l'article publié.

Purement additif (voir issue #40) : aucun des 9 agents existants n'a besoin
de le connaître. Il lit `state.article` et `state.run.status`, écrit dans
`state.linkedin_post` / `state.x_thread`, puis envoie le texte sur Telegram
pour copier-coller manuel — **aucune publication automatique** sur LinkedIn
ou X. Pas d'API gratuite fiable pour ça, et surtout : la ligne éditoriale du
projet exige un clic humain pour tout ce qui sort du blog (cf. Publisher).

Ne s'exécute que si l'article a réellement été publié (`RunStatus.PUBLISHED`,
donc poussé sur Git) — un article resté en local (❌) ou une réécriture (🔁)
ne déclenchent aucune promotion.
"""

from __future__ import annotations

from ...domain.entities.pipeline_run import RunStatus
from ...domain.ports.llm import LLMPort
from ...domain.ports.notifications import NotifierPort
from ...shared.json_utils import extract_json
from ..dto.pipeline_state import PipelineState
from ..prompts.social_writer import SOCIAL_WRITER_SYSTEM, social_writer_user_prompt
from .base import Agent


class SocialWriterAgent(Agent):
    """Génère et transmet (sur Telegram) le post LinkedIn et le thread X."""

    name = "social_writer"
    label = "Social Writer — LinkedIn & X"
    critical = False

    def __init__(
        self,
        llm: LLMPort,
        notifier: NotifierPort | None,
        *,
        blog_url: str = "",
        temperature: float = 0.6,
    ) -> None:
        super().__init__()
        self.llm = llm
        self.notifier = notifier
        self.blog_url = blog_url.rstrip("/")
        self.temperature = temperature

    # ------------------------------------------------------------------ #
    def run(self, state: PipelineState) -> PipelineState:
        if state.run.status is not RunStatus.PUBLISHED:
            self.logger.info(
                "Article non publié (statut %s) : pas de contenu social généré",
                state.run.status.value,
            )
            return state

        article = state.article
        if article is None:
            return state

        key_points = [text for level, text in article.headings if level == 2]
        article_url = f"{self.blog_url}/blog/{article.slug}" if self.blog_url else ""

        response = self.llm.generate(
            SOCIAL_WRITER_SYSTEM,
            social_writer_user_prompt(
                title=article.seo.meta_title or article.title,
                meta_description=article.seo.meta_description,
                category=article.category.value,
                angle=state.topic.angle if state.topic else "",
                key_points=key_points,
                article_url=article_url or "(lien à ajouter manuellement)",
            ),
            temperature=self.temperature,
            json_mode=True,
        )
        payload = extract_json(response.text, default={"linkedin_post": "", "x_thread": []})
        state.linkedin_post = str(payload.get("linkedin_post", "")).strip()
        state.x_thread = tuple(
            str(t).strip() for t in (payload.get("x_thread") or []) if str(t).strip()
        )

        if not state.linkedin_post and not state.x_thread:
            state.warn("Social Writer n'a produit aucun contenu exploitable")
            return state

        self._notify(state, article_url)
        self.logger.info(
            "Contenu social prêt : post LinkedIn (%s car.), thread X (%s tweet(s))",
            len(state.linkedin_post), len(state.x_thread),
        )
        return state

    # ------------------------------------------------------------------ #
    def _notify(self, state: PipelineState, article_url: str) -> None:
        if self.notifier is None:
            return
        lines = ["📣 <b>Contenu social prêt à publier</b> (copier-coller manuel)", ""]
        if state.linkedin_post:
            lines += ["<b>LinkedIn</b>", self._escape(state.linkedin_post), ""]
        if state.x_thread:
            lines.append("<b>Thread X</b>")
            lines.extend(f"{i}. {self._escape(tweet)}" for i, tweet in enumerate(state.x_thread, start=1))
            lines.append("")
        if article_url:
            lines.append(f"🔗 {article_url}")
        self.notifier.send("\n".join(lines))

    @staticmethod
    def _escape(text: str) -> str:
        """Échappe le HTML pour l'API Telegram (parse_mode=HTML)."""
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def describe(self, state: PipelineState) -> str:
        if not state.linkedin_post and not state.x_thread:
            return "aucun contenu (article non publié ou génération vide)"
        return f"post LinkedIn ({len(state.linkedin_post)} car.), thread X ({len(state.x_thread)} tweet(s))"
