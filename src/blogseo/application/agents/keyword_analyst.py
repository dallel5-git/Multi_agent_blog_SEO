"""Agent 3/9 — Keyword Analyst : choix du sujet + anti-doublon sémantique.

C'est l'agent le plus décisif du pipeline. Il :
1. croise les deux veilles + Google Trends + le retour de performance ;
2. demande au LLM UN sujet avec mots-clés et plan ;
3. **vérifie l'originalité** en interrogeant le vector store local (ChromaDB) ;
4. si le sujet est un quasi-doublon, il redemande un autre sujet (jusqu'à N fois)
   en indiquant explicitement au LLM ce qui a été rejeté.
"""

from __future__ import annotations

from ...domain.entities.series import ArticleSeries, SeriesTopic
from ...domain.entities.topic import Keyword, Topic
from ...domain.errors import DuplicateTopicError
from ...domain.ports.llm import LLMPort
from ...domain.ports.repositories import ArticleHistoryPort, SeriesRepositoryPort
from ...domain.value_objects.category import Category
from ...shared.json_utils import extract_json
from ..dto.pipeline_state import PipelineState
from ..prompts.keyword_analyst import (
    KEYWORD_ANALYST_SYSTEM,
    SERIES_SYSTEM,
    keyword_analyst_series_user_prompt,
    keyword_analyst_user_prompt,
)
from .base import Agent


class KeywordAnalystAgent(Agent):
    """Sélection du sujet du jour, garantie sans doublon."""

    name = "keyword_analyst"
    label = "Keyword Analyst — sujet et mots-clés"
    critical = True

    def __init__(
        self,
        llm: LLMPort,
        history: ArticleHistoryPort,
        *,
        duplicate_threshold: float = 0.85,
        max_attempts: int = 3,
        temperature: float = 0.4,
        series_repository: SeriesRepositoryPort | None = None,
    ) -> None:
        super().__init__()
        self.llm = llm
        self.history = history
        self.duplicate_threshold = duplicate_threshold
        self.max_attempts = max_attempts
        self.temperature = temperature
        self.series_repository = series_repository

    # ------------------------------------------------------------------ #
    def run(self, state: PipelineState) -> PipelineState:
        if self.series_repository is not None and self._consume_series_topic(state):
            return state

        global_digest = self._format_global(state)
        tunisia_digest = self._format_tunisia(state)
        trends_block = self._format_trends(state)

        last_error: DuplicateTopicError | None = None

        for attempt in range(1, self.max_attempts + 1):
            state.topic_attempts = attempt
            self.logger.info("Proposition de sujet — tentative %s/%s", attempt, self.max_attempts)

            response = self.llm.generate(
                KEYWORD_ANALYST_SYSTEM,
                keyword_analyst_user_prompt(
                    global_digest=global_digest,
                    tunisia_digest=tunisia_digest,
                    trends_block=trends_block,
                    existing_articles=state.existing_titles,
                    performance_feedback=state.performance_feedback.as_context_block(),
                    rejected_titles=state.rejected_titles,
                ),
                # On augmente la température à chaque échec pour sortir du même sujet.
                temperature=min(0.9, self.temperature + 0.2 * (attempt - 1)),
                json_mode=True,
            )
            payload = extract_json(response.text)
            topic = self._to_topic(payload)

            hit = self._check_originality(topic)
            if hit is None:
                state.topic = topic
                state.run.topic_title = topic.title
                self.logger.info(
                    "Sujet retenu : « %s » (mot-clé : %s, originalité %.0f%%)",
                    topic.title, topic.primary_keyword.term, (1 - topic.similarity_score) * 100,
                )
                return state

            last_error = DuplicateTopicError(topic.title, hit.slug, hit.score)
            self.logger.warning("Sujet rejeté (doublon) : %s", last_error)
            state.rejected_titles.append(f"{topic.title} (≈ {hit.slug})")

        # Toutes les tentatives ont produit un doublon : on arrête proprement.
        raise last_error or DuplicateTopicError("(inconnu)", "(inconnu)", 1.0)

    # ------------------------------------------------------------------ #
    # Mode série (issue #41)
    # ------------------------------------------------------------------ #
    def _consume_series_topic(self, state: PipelineState) -> bool:
        """Si une série active a un sujet en attente, l'utilise à la place du LLM.

        Renvoie True si `state.topic` a été posé depuis la file d'attente
        (aucun appel LLM), False s'il faut retomber sur la génération normale.
        """
        series = self.series_repository.find_active()
        if series is None:
            return False

        index = next(
            (i for i, t in enumerate(series.topics) if t.status == "pending"), None
        )
        if index is None:
            return False
        item = series.topics[index]

        topic = self._topic_from_series(item)
        hit = self._check_originality(topic)
        if hit is not None:
            # Le sujet planifié est devenu un doublon depuis la planification
            # (un article proche a été publié entre-temps) : on l'abandonne
            # sans bloquer le run, et on retombe sur la génération normale.
            self.logger.warning(
                "Sujet de série « %s » devenu un doublon (≈ %s) : abandonné", item.title, hit.slug
            )
            item.status = "skipped"
            self.series_repository.save(series)
            return False

        state.topic = topic
        state.run.topic_title = topic.title
        state.series_id = series.series_id
        state.series_topic_index = index
        self.logger.info(
            "Sujet de série retenu (%s, %s/%s) : « %s »",
            series.series_id, index + 1, len(series.topics), topic.title,
        )
        return True

    def plan_series(self, state: PipelineState, *, theme: str, size: int = 4) -> ArticleSeries:
        """Planifie une série de `size` sujets liés (3 à 5), anti-doublon inclus.

        Un seul appel LLM demande l'ensemble des sujets ; chacun est ensuite
        vérifié individuellement contre l'historique (`ArticleHistoryPort`),
        avec la même logique de retry à température croissante que `run()`
        pour tout créneau qui s'avère être un doublon.
        """
        response = self.llm.generate(
            SERIES_SYSTEM,
            keyword_analyst_series_user_prompt(
                theme=theme, size=size, existing_articles=state.existing_titles,
            ),
            temperature=self.temperature,
            json_mode=True,
        )
        payload = extract_json(response.text, default={})
        series_title = str(payload.get("series_title") or theme).strip()
        raw_topics = list(payload.get("topics") or [])[:size]

        topics: list[SeriesTopic] = []
        rejected: list[str] = []
        for slot in range(size):
            raw = raw_topics[slot] if slot < len(raw_topics) else {}
            topic = self._to_series_topic(raw)

            for attempt in range(1, self.max_attempts + 1):
                hit = self._check_originality(self._topic_from_series(topic))
                if hit is None:
                    break
                self.logger.warning("Sujet de série rejeté (doublon) : %s (≈ %s)", topic.title, hit.slug)
                rejected.append(f"{topic.title} (≈ {hit.slug})")
                if attempt == self.max_attempts:
                    self.logger.warning(
                        "Créneau %s/%s : aucun sujet original trouvé après %s tentatives, conservé tel quel",
                        slot + 1, size, self.max_attempts,
                    )
                    break
                retry_response = self.llm.generate(
                    SERIES_SYSTEM,
                    keyword_analyst_series_user_prompt(
                        theme=theme, size=1, existing_articles=state.existing_titles,
                        rejected_titles=rejected,
                    ),
                    temperature=min(0.9, self.temperature + 0.2 * attempt),
                    json_mode=True,
                )
                retry_payload = extract_json(retry_response.text, default={})
                replacement = (list(retry_payload.get("topics") or [{}]) or [{}])[0]
                topic = self._to_series_topic(replacement)

            topics.append(topic)

        series = ArticleSeries(theme=theme, title=series_title, topics=topics)
        self.series_repository.save(series)
        self.logger.info("Série planifiée : %s", series.summary())
        return series

    def _to_series_topic(self, raw: dict) -> SeriesTopic:
        return SeriesTopic(
            title=str(raw.get("title", "")).strip() or "(sujet à définir)",
            angle=str(raw.get("angle", "")).strip(),
            category=Category.coerce(raw.get("category")),
            primary_keyword=str(raw.get("primary_keyword", "")).strip(),
            secondary_keywords=tuple(str(k).strip() for k in (raw.get("secondary_keywords") or []) if str(k).strip()),
            outline=tuple(str(h) for h in (raw.get("outline") or []) if h),
            rationale=str(raw.get("rationale", "")).strip(),
        )

    def _topic_from_series(self, item: SeriesTopic) -> Topic:
        return Topic(
            title=item.title,
            angle=item.angle,
            category=item.category,
            primary_keyword=Keyword(term=item.primary_keyword or item.title, intent="tutorial"),
            secondary_keywords=tuple(
                Keyword(term=term, intent="informational", priority=i)
                for i, term in enumerate(item.secondary_keywords, start=2)
            ),
            rationale=item.rationale,
            outline=item.outline,
        )

    # ------------------------------------------------------------------ #
    def _check_originality(self, topic: Topic):
        """Renvoie le voisin trop proche, ou None si le sujet est original."""
        probe = f"{topic.title}. {topic.angle} {' '.join(topic.all_keyword_terms)}"
        hits = self.history.find_similar(probe, top_k=3)
        if not hits:
            topic.similarity_score = 0.0
            return None

        best = hits[0]
        topic.similarity_score = best.score
        topic.similar_slug = best.slug
        self.logger.info(
            "Anti-doublon : article le plus proche = %s (similarité %.1f%%, seuil %.0f%%)",
            best.slug, best.score * 100, self.duplicate_threshold * 100,
        )
        return best if best.score >= self.duplicate_threshold else None

    def _to_topic(self, payload: dict) -> Topic:
        """Convertit la réponse JSON du LLM en entité `Topic` valide."""
        primary_raw = payload.get("primary_keyword") or {}
        if isinstance(primary_raw, str):
            primary_raw = {"term": primary_raw}
        primary = Keyword(
            term=str(primary_raw.get("term") or payload.get("title", "")).strip(),
            intent=str(primary_raw.get("intent", "informational")),
            priority=1,
        )
        if not primary.term:
            raise ValueError("Le Keyword Analyst n'a pas fourni de mot-clé principal")

        secondary: list[Keyword] = []
        for index, raw in enumerate(payload.get("secondary_keywords") or [], start=2):
            if isinstance(raw, str):
                raw = {"term": raw}
            term = str(raw.get("term", "")).strip()
            if term:
                secondary.append(Keyword(term=term, intent=str(raw.get("intent", "informational")),
                                         priority=index))

        return Topic(
            title=str(payload.get("title", "")).strip() or primary.term,
            angle=str(payload.get("angle", "")).strip(),
            category=Category.coerce(payload.get("category")),
            primary_keyword=primary,
            secondary_keywords=tuple(secondary),
            rationale=str(payload.get("rationale", "")).strip(),
            sources=tuple(str(s) for s in (payload.get("sources") or []) if s),
            outline=tuple(str(h) for h in (payload.get("outline") or []) if h),
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _format_global(state: PipelineState) -> str:
        if state.global_themes:
            lines = [
                f"- {t.get('theme')} — {t.get('why_now', '')} "
                f"(tutoriel : {t.get('tutorial_potential', '?')}, "
                f"Tunisie : {t.get('tunisia_fit', '?')}) "
                f"sources : {', '.join(t.get('evidence', [])[:2])}"
                for t in state.global_themes
            ]
            return "\n".join(lines)
        if state.global_digest:
            return state.global_digest.as_context_block(limit=15)
        return "(veille mondiale indisponible)"

    @staticmethod
    def _format_tunisia(state: PipelineState) -> str:
        context = state.tunisia_context or {}
        if not context and state.tunisia_digest:
            return state.tunisia_digest.as_context_block(limit=15)
        if not context:
            return "(veille tunisienne indisponible)"

        facts = "\n".join(
            f"- {item.get('fact')} ({item.get('source_url', '')})"
            for item in context.get("local_context", [])
        ) or "- (aucun fait local)"
        pains = "\n".join(f"- {p}" for p in context.get("pain_points", [])) or "- (aucun)"
        angles = "\n".join(f"- {a}" for a in context.get("angles", [])) or "- (aucun)"
        return f"FAITS LOCAUX :\n{facts}\n\nPOINTS DE DOULEUR :\n{pains}\n\nANGLES :\n{angles}"

    @staticmethod
    def _format_trends(state: PipelineState) -> str:
        if not state.trends_scores:
            return "(aucune donnée Google Trends)"
        ordered = sorted(state.trends_scores.items(), key=lambda kv: kv[1], reverse=True)
        return "\n".join(f"- {term} : {score}" for term, score in ordered)

    def describe(self, state: PipelineState) -> str:
        if not state.topic:
            return "aucun sujet"
        return f"« {state.topic.title} » (originalité {(1 - state.topic.similarity_score) * 100:.0f}%)"
