"""Agent 4/9 — Content Writer : rédaction de l'article.

Deux modes :
- **première rédaction** (`state.iteration == 0`) à partir du brief du Keyword
  Analyst et de la matière de recherche ;
- **révision** quand le Quality Gate ou le Technical Reviewer ont renvoyé des
  consignes (`state.revision_instructions` non vide). C'est la boucle de
  feedback du graphe.
"""

from __future__ import annotations

from ...domain.entities.article import Article
from ...domain.ports.llm import LLMPort
from ...domain.value_objects.seo_metadata import SeoMetadata
from ...domain.value_objects.slug import Slug
from ...shared.text import strip_frontmatter, truncate
from ..dto.pipeline_state import PipelineState
from ..prompts.content_writer import (
    CONTENT_WRITER_SYSTEM,
    content_writer_revision_prompt,
    content_writer_user_prompt,
)
from .base import Agent


class ContentWriterAgent(Agent):
    """Rédacteur de l'article complet en Markdown."""

    name = "content_writer"
    label = "Content Writer — rédaction"
    critical = True

    def __init__(
        self,
        llm: LLMPort,
        *,
        min_words: int = 1200,
        max_words: int = 2000,
        temperature: float = 0.75,
        max_output_tokens: int = 8192,
        author: str = "Oussama Dallel",
    ) -> None:
        super().__init__()
        self.llm = llm
        self.min_words = min_words
        self.max_words = max_words
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.author = author

    def run(self, state: PipelineState) -> PipelineState:
        topic = state.topic
        if topic is None:
            raise ValueError("Aucun sujet disponible : le Keyword Analyst n'a rien produit")

        state.iteration += 1
        is_revision = bool(state.revision_instructions) and state.article is not None

        if is_revision:
            self.logger.info("Révision n°%s de l'article", state.iteration - 1)
            prompt = content_writer_revision_prompt(
                brief=topic.as_brief(),
                previous_article=state.article.body_markdown,
                instructions=state.revision_instructions,
                min_words=self.min_words,
                max_words=self.max_words,
                iteration=state.iteration - 1,
            )
            # Température plus basse en révision : on corrige, on ne réinvente pas.
            temperature = max(0.3, self.temperature - 0.25)
        else:
            self.logger.info("Première rédaction de « %s »", topic.title)
            prompt = content_writer_user_prompt(
                brief=topic.as_brief(),
                research_context=state.research_context or self._build_research_context(state),
                min_words=self.min_words,
                max_words=self.max_words,
            )
            temperature = self.temperature

        response = self.llm.generate(
            CONTENT_WRITER_SYSTEM,
            prompt,
            temperature=temperature,
            max_output_tokens=self.max_output_tokens,
        )
        body = self._clean(response.text)

        if is_revision:
            state.article = state.article.with_body(body)
        else:
            state.article = Article(
                title=topic.title,
                slug=Slug.from_title(topic.title),
                body_markdown=body,
                seo=SeoMetadata(
                    meta_title=truncate(topic.title, 60),
                    meta_description="",  # renseignée par le SEO Editor
                    focus_keyword=topic.primary_keyword.term,
                    secondary_keywords=tuple(k.term for k in topic.secondary_keywords),
                ),
                category=topic.category,
                tags=tuple(dict.fromkeys(
                    t.lower() for t in topic.all_keyword_terms if len(t) <= 25
                ))[:5],
                author=self.author,
                sources=topic.sources,
            )

        # La consigne de révision est consommée : elle ne doit pas resservir.
        state.revision_instructions = ""
        state.run.revision_count = state.iteration

        self.logger.info(
            "Article %s : %s mots, %s sections H2",
            "révisé" if is_revision else "rédigé",
            state.article.word_count, state.article.h2_count,
        )
        return state

    # ------------------------------------------------------------------ #
    @staticmethod
    def _clean(raw: str) -> str:
        """Nettoie la sortie du LLM : frontmatter parasite, H1, préambule."""
        body = strip_frontmatter(raw).strip()

        lines = body.splitlines()
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Un H1 dans le corps duplique le titre affiché par le site.
            if stripped.startswith("# ") and not cleaned:
                continue
            if stripped.startswith("# "):
                line = "#" + line  # on le dégrade en H2
            cleaned.append(line)
        return "\n".join(cleaned).strip()

    @staticmethod
    def _build_research_context(state: PipelineState) -> str:
        """Assemble la matière de recherche disponible pour le rédacteur."""
        blocks: list[str] = []
        if state.tunisia_context:
            facts = state.tunisia_context.get("local_context", [])
            if facts:
                blocks.append("FAITS LOCAUX VÉRIFIÉS :\n" + "\n".join(
                    f"- {f.get('fact')} (source : {f.get('source_url', 'n/a')})" for f in facts
                ))
            pains = state.tunisia_context.get("pain_points", [])
            if pains:
                blocks.append("PROBLÈMES CONCRETS DE L'AUDIENCE :\n" + "\n".join(f"- {p}" for p in pains))
        if state.global_themes:
            blocks.append("CONTEXTE TECH MONDIAL :\n" + "\n".join(
                f"- {t.get('theme')} : {t.get('why_now', '')}" for t in state.global_themes[:5]
            ))
        if state.global_digest:
            blocks.append("SOURCES BRUTES :\n" + state.global_digest.as_context_block(limit=8))
        return "\n\n".join(blocks) or "(aucune matière de recherche disponible)"

    def describe(self, state: PipelineState) -> str:
        if not state.article:
            return "aucun article"
        return f"{state.article.word_count} mots, {state.article.h2_count} sections (rév. {state.iteration})"
