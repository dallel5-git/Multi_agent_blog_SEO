"""Agent 6/9 — SEO Editor : métadonnées, slug, maillage interne, alt-text.

Le LLM propose ; l'agent **valide et corrige** de façon déterministe (longueurs,
présence du mot-clé, slugs internes réellement existants). Aucune valeur non
conforme ne sort de cet agent.
"""

from __future__ import annotations

from ...domain.ports.llm import LLMPort
from ...domain.value_objects.seo_metadata import (
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    TITLE_MAX,
    SeoMetadata,
    contains_keyword,
)
from ...domain.value_objects.slug import Slug
from ...shared.text import truncate
from ..dto.pipeline_state import PipelineState
from ..prompts.reviewing import SEO_EDITOR_SYSTEM, seo_editor_user_prompt
from .base import Agent


class SeoEditorAgent(Agent):
    """Optimisation des métadonnées SEO."""

    name = "seo_editor"
    label = "SEO Editor — métadonnées et maillage"
    critical = True

    def __init__(self, llm: LLMPort, *, temperature: float = 0.3, max_internal_links: int = 3) -> None:
        super().__init__()
        self.llm = llm
        self.temperature = temperature
        self.max_internal_links = max_internal_links

    def run(self, state: PipelineState) -> PipelineState:
        article = state.article
        topic = state.topic
        if article is None or topic is None:
            raise ValueError("SEO Editor : article ou sujet manquant")

        existing_slugs = state.existing_slugs
        response = self.llm.generate(
            SEO_EDITOR_SYSTEM,
            seo_editor_user_prompt(
                working_title=article.title,
                primary_keyword=topic.primary_keyword.term,
                secondary_keywords=[k.term for k in topic.secondary_keywords],
                article_excerpt=article.body_markdown[:1500],
                existing_slugs=existing_slugs,
                existing_tags=state.existing_tags,
            ),
            temperature=self.temperature,
            json_mode=True,
        )
        from ...shared.json_utils import extract_json

        payload = extract_json(response.text, default={})

        focus = str(payload.get("focus_keyword") or topic.primary_keyword.term).strip()
        meta_title = self._fix_title(str(payload.get("meta_title") or article.title), focus)
        meta_description = self._fix_description(
            str(payload.get("meta_description") or ""), focus, article.body_markdown
        )
        internal_links = self._fix_internal_links(payload.get("internal_links"), existing_slugs)

        seo = SeoMetadata(
            meta_title=meta_title,
            meta_description=meta_description,
            focus_keyword=focus,
            secondary_keywords=tuple(
                str(k).strip() for k in (payload.get("secondary_keywords") or []) if str(k).strip()
            )[:5],
            internal_links=internal_links,
            cover_alt_text=str(payload.get("cover_alt_text") or f"Illustration : {meta_title}").strip(),
        )

        article = article.with_seo(seo)
        article.slug = self._fix_slug(payload.get("slug"), meta_title, existing_slugs)
        article.tags = self._fix_tags(payload.get("tags"), topic)
        article.body_markdown = self._inject_internal_links(article.body_markdown, internal_links, state)

        state.article = article
        state.run.article_slug = article.slug.value

        issues = seo.all_issues()
        if issues:
            self.logger.warning("Métadonnées encore imparfaites : %s", " ; ".join(issues))
        self.logger.info(
            "SEO : titre %s car., description %s car., slug « %s », %s lien(s) interne(s)",
            len(meta_title), len(meta_description), article.slug.value, len(internal_links),
        )
        return state

    # ------------------------------------------------------------------ #
    @staticmethod
    def _fix_title(title: str, focus: str) -> str:
        """Garantit un meta title exploitable : mot-clé présent et longueur bornée.

        Priorité au sens : on ne remplace jamais un titre lisible par le seul
        mot-clé. Si le préfixage ne tient pas dans les 60 caractères, on garde
        le titre d'origine tronqué et le Quality Gate émettra un avertissement.
        """
        title = title.strip().strip('"').rstrip(".")
        if not contains_keyword(title, focus):
            candidate = f"{focus.capitalize()} : {title}"
            if len(candidate) <= TITLE_MAX:
                return candidate
        return truncate(title, TITLE_MAX, suffix="")

    @staticmethod
    def _fix_description(description: str, focus: str, body: str) -> str:
        """Complète ou tronque la description pour rester dans la fenêtre Google."""
        description = " ".join(description.split()).strip().strip('"')

        if len(description) < DESCRIPTION_MIN:
            # On complète avec le début du corps, nettoyé de son Markdown.
            filler = " ".join(
                line.strip("#* ") for line in body.splitlines()
                if line.strip() and not line.strip().startswith(("#", "`", "<", "-"))
            )
            description = (description + " " + filler).strip()

        if not contains_keyword(description, focus):
            description = f"{focus.capitalize()} : {description}"

        if len(description) > DESCRIPTION_MAX:
            description = truncate(description, DESCRIPTION_MAX, suffix="")
        return description.rstrip(" ,;:").rstrip(".") + "."

    @staticmethod
    def _fix_slug(raw, meta_title: str, existing_slugs: list[str]) -> Slug:
        """Slug valide, dérivé du titre si le LLM en propose un incorrect."""
        try:
            slug = Slug(str(raw).strip()) if raw else Slug.from_title(meta_title)
        except ValueError:
            slug = Slug.from_title(str(raw) if raw else meta_title)

        # Collision avec un article existant → on suffixe.
        if slug.value in existing_slugs:
            for suffix in range(2, 20):
                candidate = f"{slug.value}-{suffix}"
                if candidate not in existing_slugs:
                    return Slug(candidate)
        return slug

    def _fix_internal_links(self, raw, existing_slugs: list[str]) -> tuple[str, ...]:
        """Ne conserve que les slugs qui existent réellement dans le blog."""
        if not isinstance(raw, list):
            return ()
        valid = [str(s).strip() for s in raw if str(s).strip() in existing_slugs]
        dropped = len(raw) - len(valid)
        if dropped:
            self.logger.warning("%s lien(s) interne(s) inventé(s) par le LLM ont été retirés", dropped)
        return tuple(dict.fromkeys(valid))[: self.max_internal_links]

    @staticmethod
    def _fix_tags(raw, topic) -> tuple[str, ...]:
        """3 à 5 tags, en minuscules, sans doublon."""
        tags = [str(t).strip().lower() for t in (raw or []) if str(t).strip()]
        if len(tags) < 3:
            tags += [t.lower() for t in topic.all_keyword_terms]
        clean = [t for t in dict.fromkeys(tags) if 2 <= len(t) <= 25]
        return tuple(clean[:5])

    def _inject_internal_links(self, body: str, links: tuple[str, ...], state: PipelineState) -> str:
        """Ajoute une section « À lire aussi » si le maillage interne est pertinent.

        On n'insère pas les liens au milieu du texte (risque de casser le sens) :
        une section dédiée en fin d'article est plus sûre et tout aussi efficace
        pour le maillage interne.
        """
        if not links or "## À lire aussi" in body:
            return body

        titles = {ref.slug: ref.title for ref in state.existing_articles}
        lines = [f"- [{titles.get(slug, slug)}](/blog/{slug})" for slug in links]
        return body.rstrip() + "\n\n## À lire aussi\n\n" + "\n".join(lines) + "\n"

    def describe(self, state: PipelineState) -> str:
        if not state.article:
            return "aucun article"
        seo = state.article.seo
        return f"slug « {state.article.slug} », titre {len(seo.meta_title)} car."
