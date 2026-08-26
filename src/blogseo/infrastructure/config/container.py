"""Composition root : c'est le SEUL endroit où les couches se rencontrent.

Le domain ne connaît personne. L'application ne connaît que les ports.
L'infrastructure implémente les ports. Ce conteneur câble le tout.

Conséquence pratique : pour remplacer Gemini par un autre modèle, DuckDuckGo par
un autre moteur ou Telegram par Slack, on ne modifie que ce fichier.
"""

from __future__ import annotations

import logging
from functools import cached_property

from ...application.agents.analytics_tracker import AnalyticsTrackerAgent
from ...application.agents.content_writer import ContentWriterAgent
from ...application.agents.keyword_analyst import KeywordAnalystAgent
from ...application.agents.publisher import PublisherAgent
from ...application.agents.quality_gate import QualityGateAgent
from ...application.agents.seo_editor import SeoEditorAgent
from ...application.agents.social_writer import SocialWriterAgent
from ...application.agents.technical_reviewer import TechnicalReviewerAgent
from ...application.agents.trend_scout import TrendScoutAgent
from ...application.agents.tunisia_watcher import TunisiaWatcherAgent
from ...domain.entities.pipeline_run import Decision
from ...domain.entities.trend import TrendOrigin
from ...domain.ports.analytics import AnalyticsPort
from ...domain.ports.llm import LLMPort
from ...domain.ports.search import SearchPort, TrendsPort
from ...orchestrator.graph import build_orchestrator
from ...orchestrator.pipeline_spec import AgentBundle
from ...shared.rate_limiter import RateLimitConfig, RateLimiter
from ..analytics.search_console import SearchConsoleAnalytics
from ..analytics.stub import FileAnalyticsStub
from ..embeddings.sentence_transformers_adapter import SentenceTransformerEmbeddings
from ..images.pollinations import PollinationsImageGenerator
from ..llm.fake import FakeLLM
from ..llm.fallback_chain import FallbackLLM
from ..llm.gemini import GeminiLLM
from ..llm.groq import GroqLLM
from ..llm.openrouter import OpenRouterLLM
from ..notifications.telegram import NullNotifier, TelegramBot
from ..persistence.json_run_repository import JsonRunRepository
from ..persistence.json_series_repository import JsonSeriesRepository
from ..persistence.mdx_article_source import MdxArticleSource
from ..publishing.article_refresher import MdxArticleRefresher
from ..publishing.git_publisher import GitPublisher
from ..publishing.mdx_writer import MdxArticleWriter
from ..publishing.series_linker import SeriesBacklinkWriter
from ..search.composite import CompositeSearch
from ..search.duckduckgo import DuckDuckGoSearch
from ..search.null_search import NullSearch
from ..search.tavily import TavilySearch
from ..sources.devto import DevToSource
from ..sources.hackernews import HackerNewsSource
from ..sources.reddit import RedditSource
from ..sources.rss import DEFAULT_GLOBAL_FEEDS, RssSource
from ..trends.null_trends import NullTrends
from ..trends.pytrends_adapter import PyTrendsAdapter
from ..vectorstore.chroma_history import ChromaArticleHistory
from .settings import Settings

logger = logging.getLogger(__name__)


class Container:
    """Conteneur d'injection de dépendances, construit paresseusement."""

    def __init__(self, settings: Settings, *, offline: bool = False) -> None:
        self.settings = settings
        self.offline = offline
        self.settings.storage.ensure()

    # ------------------------------------------------------------------ #
    # LLM
    # ------------------------------------------------------------------ #
    @cached_property
    def llm(self) -> LLMPort:
        """Chaîne Groq → OpenRouter (2 modèles) → Gemini (voir ADR 0008), ou LLM
        factice en mode hors ligne. Seuls les fournisseurs dont la clé est
        configurée entrent dans la chaîne."""
        if self.offline:
            logger.warning("Mode hors ligne : LLM factice (aucun appel réseau)")
            return FakeLLM(article_words=self.settings.content.min_words + 200)

        cfg = self.settings.llm
        providers: list[LLMPort] = []

        if cfg.groq_api_key:
            providers.append(GroqLLM(
                cfg.groq_api_key,
                cfg.groq_model,
                rate_limiter=RateLimiter(
                    "groq",
                    RateLimitConfig(cfg.groq_rpm, cfg.groq_rpd, min_interval_s=0.5),
                    state_file=self.settings.storage.rate_limits / "groq.json",
                ),
                timeout_s=cfg.timeout_s,
            ))
        if cfg.openrouter_api_key:
            # Deux modèles OpenRouter distincts sous la même clé : `name` différencié
            # pour que FallbackLLM ne confonde pas leur suivi de quota/usage.
            providers.append(OpenRouterLLM(
                cfg.openrouter_api_key,
                cfg.openrouter_model,
                name="openrouter",
                rate_limiter=RateLimiter(
                    "openrouter",
                    RateLimitConfig(cfg.openrouter_rpm, cfg.openrouter_rpd, min_interval_s=1.0),
                    state_file=self.settings.storage.rate_limits / "openrouter.json",
                ),
                timeout_s=cfg.timeout_s,
            ))
            providers.append(OpenRouterLLM(
                cfg.openrouter_api_key,
                cfg.openrouter_model_2,
                name="openrouter-2",
                rate_limiter=RateLimiter(
                    "openrouter-2",
                    RateLimitConfig(cfg.openrouter_rpm, cfg.openrouter_rpd, min_interval_s=1.0),
                    state_file=self.settings.storage.rate_limits / "openrouter-2.json",
                ),
                timeout_s=cfg.timeout_s,
            ))
        if cfg.gemini_api_key:
            providers.append(GeminiLLM(
                cfg.gemini_api_key,
                cfg.gemini_model,
                rate_limiter=RateLimiter(
                    "gemini",
                    RateLimitConfig(cfg.gemini_rpm, cfg.gemini_rpd, min_interval_s=1.0),
                    state_file=self.settings.storage.rate_limits / "gemini.json",
                ),
                timeout_s=cfg.timeout_s,
            ))

        if not providers:
            logger.warning(
                "Aucune clé LLM configurée (GROQ_API_KEY / OPENROUTER_API_KEY / "
                "GEMINI_API_KEY) : bascule automatique sur le LLM factice. Les "
                "articles seront des exemples."
            )
            return FakeLLM(article_words=self.settings.content.min_words + 200)

        logger.info("Chaîne LLM : %s", " → ".join(p.name for p in providers))
        return FallbackLLM(providers)

    # ------------------------------------------------------------------ #
    # Recherche et veille
    # ------------------------------------------------------------------ #
    @cached_property
    def search(self) -> SearchPort:
        if self.offline:
            return NullSearch()
        engines = [DuckDuckGoSearch(delay_s=self.settings.search.request_delay_s)]
        if self.settings.search.tavily_api_key:
            engines.append(TavilySearch(self.settings.search.tavily_api_key))
        return CompositeSearch(engines)

    @cached_property
    def trends(self) -> TrendsPort:
        if self.offline:
            return NullTrends()
        return PyTrendsAdapter()

    @cached_property
    def global_sources(self) -> list:
        if self.offline:
            logger.warning("Mode hors ligne : veille mondiale désactivée (aucun appel réseau)")
            return []
        cfg = self.settings.sources
        return [
            HackerNewsSource(limit=cfg.hackernews_limit, timeout_s=cfg.http_timeout_s,
                             user_agent=cfg.user_agent),
            RedditSource(cfg.reddit_subreddits, limit=cfg.reddit_limit,
                         timeout_s=cfg.http_timeout_s, user_agent=cfg.user_agent),
            DevToSource(cfg.devto_tags, limit=cfg.devto_limit,
                        timeout_s=cfg.http_timeout_s, user_agent=cfg.user_agent),
            RssSource(DEFAULT_GLOBAL_FEEDS, label="Product Hunt & blogs outils",
                      timeout_s=cfg.http_timeout_s, user_agent=cfg.user_agent),
        ]

    @cached_property
    def tunisia_rss(self) -> RssSource | None:
        if self.offline:
            return None
        feeds = self.settings.sources.tunisia_rss_feeds
        if not feeds:
            return None
        return RssSource(
            feeds, origin=TrendOrigin.TUNISIA, label="Médias tech tunisiens",
            timeout_s=self.settings.sources.http_timeout_s,
            user_agent=self.settings.sources.user_agent,
        )

    # ------------------------------------------------------------------ #
    # Persistance et anti-doublon
    # ------------------------------------------------------------------ #
    @cached_property
    def embeddings(self) -> SentenceTransformerEmbeddings:
        return SentenceTransformerEmbeddings(self.settings.embedding_model)

    @cached_property
    def history(self) -> ChromaArticleHistory:
        return ChromaArticleHistory(self.embeddings, self.settings.storage.chroma)

    @cached_property
    def article_source(self) -> MdxArticleSource:
        return MdxArticleSource(self.settings.publishing.blog_content_dir)

    @cached_property
    def run_repository(self) -> JsonRunRepository:
        return JsonRunRepository(self.settings.storage.runs)

    @cached_property
    def series_repository(self) -> JsonSeriesRepository:
        return JsonSeriesRepository(self.settings.storage.series)

    @cached_property
    def series_linker(self) -> SeriesBacklinkWriter:
        return SeriesBacklinkWriter(self.settings.publishing.blog_content_dir)

    @cached_property
    def article_refresher(self) -> MdxArticleRefresher:
        return MdxArticleRefresher(self.settings.publishing.blog_content_dir)

    @cached_property
    def analytics(self) -> AnalyticsPort:
        """Search Console si configuré (et en ligne), sinon repli sur l'export manuel."""
        cfg = self.settings.search_console
        if not self.offline and cfg.is_configured:
            return SearchConsoleAnalytics(
                site_url=cfg.site_url,
                client_id=cfg.client_id,
                client_secret=cfg.client_secret,
                refresh_token=cfg.refresh_token,
            )
        return FileAnalyticsStub(self.settings.storage.root / "analytics" / "performance.json")

    # ------------------------------------------------------------------ #
    # Publication et notifications
    # ------------------------------------------------------------------ #
    @cached_property
    def writer(self) -> MdxArticleWriter:
        return MdxArticleWriter(self.settings.storage.drafts)

    @cached_property
    def git(self) -> GitPublisher | None:
        repo = self.settings.publishing.blog_repo_dir
        if not (repo / ".git").exists():
            logger.warning(
                "%s n'est pas un dépôt Git : la publication automatique sera désactivée "
                "(l'article sera quand même écrit sur disque).", repo,
            )
            return None
        cfg = self.settings.publishing
        return GitPublisher(repo, branch=cfg.git_branch, remote=cfg.git_remote,
                            user_name=cfg.git_user_name, user_email=cfg.git_user_email)

    @cached_property
    def image_generator(self) -> PollinationsImageGenerator | None:
        if not self.settings.publishing.enable_cover_generation or self.offline:
            return None
        return PollinationsImageGenerator(self.settings.storage.covers)

    @cached_property
    def telegram(self):
        cfg = self.settings.telegram
        if not cfg.is_configured or self.offline:
            reason = "mode hors ligne" if self.offline else "TELEGRAM_BOT_TOKEN/CHAT_ID absents"
            logger.warning("Telegram inactif (%s) : décision par défaut = écriture locale", reason)
            return NullNotifier(default_decision=Decision.REJECT)
        return TelegramBot(
            cfg.bot_token, cfg.chat_id,
            state_dir=self.settings.storage.root,
            poll_interval_s=cfg.poll_interval_s,
        )

    # ------------------------------------------------------------------ #
    # Agents
    # ------------------------------------------------------------------ #
    @cached_property
    def agents(self) -> AgentBundle:
        s = self.settings
        llm = self.llm

        return AgentBundle(
            trend_scout=TrendScoutAgent(self.global_sources, llm),
            tunisia_watcher=TunisiaWatcherAgent(
                self.search, self.trends, llm,
                queries=s.sources.tunisia_queries,
                rss_source=self.tunisia_rss,
                max_results=s.search.max_results,
            ),
            keyword_analyst=KeywordAnalystAgent(
                llm, self.history,
                duplicate_threshold=s.content.duplicate_threshold,
                temperature=s.llm.temperature_analytic,
                series_repository=self.series_repository,
            ),
            content_writer=ContentWriterAgent(
                llm,
                min_words=s.content.min_words,
                max_words=s.content.max_words,
                temperature=s.llm.temperature_creative,
                max_output_tokens=s.llm.max_output_tokens,
                author=s.content.author,
            ),
            technical_reviewer=TechnicalReviewerAgent(
                llm, check_links=not self.offline, temperature=s.llm.temperature_analytic
            ),
            seo_editor=SeoEditorAgent(llm, temperature=s.llm.temperature_analytic),
            quality_gate=QualityGateAgent(
                min_words=s.content.min_words,
                max_words=s.content.max_words,
                min_h2=s.content.min_h2,
                min_keyword_density=s.content.min_keyword_density,
                max_keyword_density=s.content.max_keyword_density,
                tunisia_terms=s.content.required_tunisia_terms,
                duplicate_threshold=s.content.duplicate_threshold,
            ),
            publisher=PublisherAgent(
                self.writer,
                drafts_dir=s.storage.drafts,
                blog_content_dir=s.publishing.blog_content_dir,
                git=self.git,
                image_generator=self.image_generator,
                cover_output_dir=s.publishing.cover_public_dir,
                cover_url_prefix=s.publishing.cover_url_prefix,
                notifier=self.telegram,
                reviewer=self.telegram,
                human_review=s.human_review,
                review_timeout_s=s.telegram.review_timeout_s,
                default_on_timeout=(
                    Decision.APPROVE if s.telegram.default_on_timeout == "approve" else Decision.REJECT
                ),
                commit_prefix=s.publishing.commit_prefix,
                blog_url=s.content.blog_url,
                series_repository=self.series_repository,
                series_linker=self.series_linker,
            ),
            social_writer=SocialWriterAgent(
                llm, self.telegram,
                blog_url=s.content.blog_url,
                temperature=s.llm.temperature_creative,
            ),
            analytics_tracker=AnalyticsTrackerAgent(self.analytics, self.history),
        )

    @cached_property
    def orchestrator(self):
        return build_orchestrator(
            self.agents,
            preferred=self.settings.orchestrator,
            max_revisions=self.settings.content.max_revisions,
        )
