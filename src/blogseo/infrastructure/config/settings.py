"""Configuration centralisée, lue exclusivement depuis l'environnement.

Règle absolue du projet : **aucune clé d'API n'est jamais écrite en dur**.
Tout passe par des variables d'environnement, chargées depuis `.env` en local
via python-dotenv (optionnel : si le paquet est absent, on lit l'environnement
système directement).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..sources.rss import DEFAULT_TUNISIA_FEEDS

logger = logging.getLogger(__name__)

# Racine du projet = 4 niveaux au-dessus de ce fichier.
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# --------------------------------------------------------------------------- #
# Chemins par défaut du blog Next.js sur le poste de l'auteur.
# Déclarés comme constantes de module (et non comme attributs de classe) car
# les dataclasses `slots=True` ne permettent pas de relire leurs valeurs par
# défaut via la classe : `PublishingSettings.blog_repo_dir` renverrait le
# descripteur de slot, pas le chemin.
# --------------------------------------------------------------------------- #
_BLOG_BASE = Path("/home/oussama/Bureau/Chaine_youtube_Oussama_Dallel/Blog IA/oussama-blog")
DEFAULT_BLOG_REPO_DIR = _BLOG_BASE
DEFAULT_BLOG_CONTENT_DIR = _BLOG_BASE / "content" / "articles"
DEFAULT_BLOG_COVER_DIR = _BLOG_BASE / "public" / "covers"


def _load_dotenv() -> None:
    """Charge `.env` si python-dotenv est installé (jamais obligatoire)."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        load_dotenv(env_file, override=False)
    except ImportError:  # pragma: no cover - repli sans dépendance
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key, str(default)).lower()
    return raw in {"1", "true", "yes", "y", "on", "oui"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_list(key: str, default: str = "") -> tuple[str, ...]:
    raw = _env(key, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


# --------------------------------------------------------------------------- #
# Sections de configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Chaîne LLM 100 % free tier, dans cet ordre (voir ADR 0008) :

    Groq → OpenRouter (2 modèles) → Gemini. Cerebras a été retiré : le compte
    testé exige une facturation activée pour l'inférence (HTTP 402), ce qui
    viole la contrainte « jamais de carte bancaire » du projet (ADR 0003) —
    ce n'est pas une panne ponctuelle de compte comme pour Gemini (ADR 0006),
    mais une caractéristique du produit. L'adapter `CerebrasLLM` reste dans
    le code pour qui a un compte sans cette restriction.

    OpenRouter occupe deux maillons (`openrouter_model`/`openrouter_model_2`)
    sous la même clé : plusieurs modèles `:free` différents plutôt qu'un
    seul, pour absorber le cas où l'un d'eux devient payant ou est
    rate-limité (déjà observé lors des tests).
    """

    groq_api_key: str = ""
    # llama-3.3-70b-versatile n'existe plus chez Groq (HTTP 404) ; openai/gpt-oss-20b
    # est rapide, gratuit, et compatible avec le mode JSON strict utilisé par les agents.
    groq_model: str = "openai/gpt-oss-20b"
    groq_rpm: int = 30
    groq_rpd: int = 14_400

    openrouter_api_key: str = ""
    # meta-llama/llama-3.3-70b-instruct:free est devenu payant (HTTP 404 avec
    # message de migration) ; nemotron-3-super-120b répond correctement en
    # texte simple ET en JSON strict (vérifié).
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    # Second modèle, même clé : gpt-oss-20b:free fonctionne en texte simple
    # mais peut être rate-limité indépendamment du premier modèle.
    openrouter_model_2: str = "openai/gpt-oss-20b:free"
    openrouter_rpm: int = 20
    openrouter_rpd: int = 200  # OpenRouter free tier : ~50-1000/jour selon les crédits du compte

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_rpm: int = 15
    gemini_rpd: int = 1_500

    temperature_creative: float = 0.75  # Content Writer
    temperature_analytic: float = 0.25  # Keyword Analyst, SEO Editor, Reviewer
    max_output_tokens: int = 8_192
    timeout_s: int = 120

    @property
    def has_any_provider(self) -> bool:
        return bool(self.groq_api_key or self.openrouter_api_key or self.gemini_api_key)


@dataclass(frozen=True, slots=True)
class SearchSettings:
    """Recherche web : DuckDuckGo sans clé, Tavily free tier en option."""

    tavily_api_key: str = ""
    max_results: int = 8
    region_global: str = "wt-wt"
    region_tunisia: str = "fr-tn"
    request_delay_s: float = 2.0  # DuckDuckGo rate-limite agressivement


@dataclass(frozen=True, slots=True)
class SourcesSettings:
    """Sources de veille tech gratuites et publiques."""

    hackernews_limit: int = 20
    devto_tags: tuple[str, ...] = ("ai", "automation", "python", "webdev")
    devto_limit: int = 20
    reddit_subreddits: tuple[str, ...] = (
        "artificial", "LocalLLaMA", "n8n", "automation", "Python", "AI_Agents",
    )
    reddit_limit: int = 15
    tunisia_rss_feeds: tuple[str, ...] = DEFAULT_TUNISIA_FEEDS
    tunisia_queries: tuple[str, ...] = (
        # Génériques (IA, automatisation, numérique).
        "startup Tunisie intelligence artificielle",
        "PME tunisienne digitalisation automatisation",
        "Tunisie développeurs IA freelance",
        "loi startup act Tunisie numérique",
        # Secteurs.
        "fintech Tunisie startup",
        "agritech Tunisie innovation numérique",
        # Villes (écosystèmes tech en dehors de Tunis).
        "Sfax Sousse écosystème tech startup",
        # Programmes d'accompagnement.
        "Smart Tunisia Flat6Labs Tunis programme startups",
    )
    user_agent: str = "blogseo-agents/1.0 (+https://github.com/dallel5-git/Multi_agent_blog_SEO)"
    http_timeout_s: int = 20


@dataclass(frozen=True, slots=True)
class ContentSettings:
    """Ligne éditoriale et règles du Quality Gate."""

    language: str = "fr"
    min_words: int = 1_200
    max_words: int = 2_000
    min_h2: int = 4
    max_revisions: int = 2  # nombre de retours Quality Gate → Content Writer
    duplicate_threshold: float = 0.85  # similarité cosinus au-delà de laquelle on rejette
    min_keyword_density: float = 0.003
    max_keyword_density: float = 0.025
    required_tunisia_terms: tuple[str, ...] = (
        "tunis", "tunisie", "tunisien", "tunisienne", "dinar", "tnd", "maghreb",
    )
    author: str = "Oussama Dallel"
    youtube_channel: str = "https://www.youtube.com/@oussamadallel5"
    portfolio_url: str = "https://oussama-ai-blog-v1.vercel.app/"
    blog_url: str = "https://oussama-ai-blog-v1.vercel.app"


@dataclass(frozen=True, slots=True)
class PublishingSettings:
    """Où et comment l'article est écrit / publié."""

    # Dossier `content/articles` du blog Next.js sur le poste de l'auteur.
    blog_content_dir: Path = DEFAULT_BLOG_CONTENT_DIR
    blog_repo_dir: Path = DEFAULT_BLOG_REPO_DIR
    git_branch: str = "main"
    git_remote: str = "origin"
    git_user_name: str = "blogseo-bot"
    git_user_email: str = "bot@oussamadallel.local"
    commit_prefix: str = "content:"
    cover_width: int = 1280
    cover_height: int = 720
    # Chemin public de l'image, relatif à `public/` du blog Next.js.
    cover_public_dir: Path = DEFAULT_BLOG_COVER_DIR
    cover_url_prefix: str = "/covers"
    enable_cover_generation: bool = True


@dataclass(frozen=True, slots=True)
class TelegramSettings:
    """Validation humaine et notifications."""

    bot_token: str = ""
    chat_id: str = ""
    review_timeout_s: int = 86_400  # 24 h d'attente maximum
    poll_interval_s: int = 5
    # Action appliquée si aucune réponse dans le délai : par défaut, on garde en local.
    default_on_timeout: str = "reject"

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass(frozen=True, slots=True)
class SearchConsoleSettings:
    """Boucle de rétroaction performance — OAuth Search Console (gratuit).

    Voir `scripts/search_console_oauth.py` pour obtenir `refresh_token`, et la
    section 10 de `.env.example` pour la création des identifiants OAuth.
    """

    site_url: str = ""       # ex. "https://oussama-ai-blog-v1.vercel.app/" ou "sc-domain:exemple.com"
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.site_url and self.client_id and self.client_secret and self.refresh_token)


@dataclass(frozen=True, slots=True)
class StorageSettings:
    """Chemins locaux du projet (jamais dans le dépôt du blog)."""

    root: Path = PROJECT_ROOT / "storage"

    @property
    def drafts(self) -> Path:
        return self.root / "drafts"

    @property
    def pending(self) -> Path:
        return self.root / "pending"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def chroma(self) -> Path:
        return self.root / "chroma"

    @property
    def covers(self) -> Path:
        return self.root / "covers"

    @property
    def rate_limits(self) -> Path:
        return self.root / "rate_limits"

    def ensure(self) -> None:
        for path in (self.drafts, self.pending, self.runs, self.logs,
                     self.chroma, self.covers, self.rate_limits):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class Settings:
    """Agrégat de configuration injecté dans le conteneur."""

    llm: LLMSettings = field(default_factory=LLMSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    sources: SourcesSettings = field(default_factory=SourcesSettings)
    content: ContentSettings = field(default_factory=ContentSettings)
    publishing: PublishingSettings = field(default_factory=PublishingSettings)
    telegram: TelegramSettings = field(default_factory=TelegramSettings)
    search_console: SearchConsoleSettings = field(default_factory=SearchConsoleSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)

    human_review: bool = True
    dry_run: bool = False
    log_level: str = "INFO"
    orchestrator: str = "langgraph"  # "langgraph" | "sequential"
    embedding_model: str = "all-MiniLM-L6-v2"

    # ------------------------------------------------------------------ #
    @classmethod
    def from_env(cls) -> Settings:
        """Construit la configuration depuis l'environnement (+ `.env`)."""
        _load_dotenv()

        blog_content = _env("BLOG_CONTENT_DIR", str(DEFAULT_BLOG_CONTENT_DIR))
        blog_repo = _env("BLOG_REPO_DIR", str(DEFAULT_BLOG_REPO_DIR))
        cover_dir = _env("BLOG_COVER_DIR", str(DEFAULT_BLOG_COVER_DIR))

        return cls(
            llm=LLMSettings(
                groq_api_key=_env("GROQ_API_KEY"),
                groq_model=_env("GROQ_MODEL", "openai/gpt-oss-20b"),
                groq_rpm=_env_int("GROQ_RPM", 30),
                groq_rpd=_env_int("GROQ_RPD", 14_400),
                openrouter_api_key=_env("OPENROUTER_API_KEY"),
                openrouter_model=_env("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
                openrouter_model_2=_env("OPENROUTER_MODEL_2", "openai/gpt-oss-20b:free"),
                openrouter_rpm=_env_int("OPENROUTER_RPM", 20),
                openrouter_rpd=_env_int("OPENROUTER_RPD", 200),
                gemini_api_key=_env("GEMINI_API_KEY"),
                gemini_model=_env("GEMINI_MODEL", "gemini-3.6-flash"),
                gemini_rpm=_env_int("GEMINI_RPM", 15),
                gemini_rpd=_env_int("GEMINI_RPD", 1_500),
                temperature_creative=_env_float("LLM_TEMPERATURE_CREATIVE", 0.75),
                temperature_analytic=_env_float("LLM_TEMPERATURE_ANALYTIC", 0.25),
                max_output_tokens=_env_int("LLM_MAX_OUTPUT_TOKENS", 8_192),
                timeout_s=_env_int("LLM_TIMEOUT_S", 120),
            ),
            search=SearchSettings(
                tavily_api_key=_env("TAVILY_API_KEY"),
                max_results=_env_int("SEARCH_MAX_RESULTS", 8),
                request_delay_s=_env_float("SEARCH_DELAY_S", 2.0),
            ),
            sources=SourcesSettings(
                hackernews_limit=_env_int("HN_LIMIT", 20),
                devto_tags=_env_list("DEVTO_TAGS", "ai,automation,python,webdev"),
                reddit_subreddits=_env_list(
                    "REDDIT_SUBREDDITS",
                    "artificial,LocalLLaMA,n8n,automation,Python,AI_Agents",
                ),
                tunisia_rss_feeds=_env_list("TUNISIA_RSS_FEEDS", ",".join(DEFAULT_TUNISIA_FEEDS)),
            ),
            content=ContentSettings(
                min_words=_env_int("ARTICLE_MIN_WORDS", 1_200),
                max_words=_env_int("ARTICLE_MAX_WORDS", 2_000),
                max_revisions=_env_int("MAX_REVISIONS", 2),
                duplicate_threshold=_env_float("DUPLICATE_THRESHOLD", 0.85),
                author=_env("ARTICLE_AUTHOR", "Oussama Dallel"),
            ),
            publishing=PublishingSettings(
                blog_content_dir=Path(blog_content).expanduser(),
                blog_repo_dir=Path(blog_repo).expanduser(),
                git_branch=_env("BLOG_GIT_BRANCH", "main"),
                git_remote=_env("BLOG_GIT_REMOTE", "origin"),
                cover_public_dir=Path(cover_dir).expanduser(),
                enable_cover_generation=_env_bool("ENABLE_COVER_GENERATION", True),
            ),
            telegram=TelegramSettings(
                bot_token=_env("TELEGRAM_BOT_TOKEN"),
                chat_id=_env("TELEGRAM_CHAT_ID"),
                review_timeout_s=_env_int("TELEGRAM_REVIEW_TIMEOUT_S", 86_400),
                poll_interval_s=_env_int("TELEGRAM_POLL_INTERVAL_S", 5),
                default_on_timeout=_env("TELEGRAM_DEFAULT_ON_TIMEOUT", "reject"),
            ),
            search_console=SearchConsoleSettings(
                site_url=_env("SEARCH_CONSOLE_SITE_URL"),
                client_id=_env("SEARCH_CONSOLE_CLIENT_ID"),
                client_secret=_env("SEARCH_CONSOLE_CLIENT_SECRET"),
                refresh_token=_env("SEARCH_CONSOLE_REFRESH_TOKEN"),
            ),
            storage=StorageSettings(root=Path(_env("STORAGE_DIR", str(PROJECT_ROOT / "storage")))),
            human_review=_env_bool("HUMAN_REVIEW", True),
            dry_run=_env_bool("DRY_RUN", False),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
            orchestrator=_env("ORCHESTRATOR", "langgraph").lower(),
            embedding_model=_env("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        )

    def describe(self) -> str:
        """Résumé lisible, sans jamais afficher une clé (uniquement présente/absente)."""
        def flag(value: str) -> str:
            return "✅ configurée" if value else "❌ absente"

        return "\n".join([
            f"  LLM (ordre)     : 1. Groq ({self.llm.groq_model}) — clé {flag(self.llm.groq_api_key)}",
            f"                    2. OpenRouter ({self.llm.openrouter_model}) — clé {flag(self.llm.openrouter_api_key)}",
            f"                    3. OpenRouter ({self.llm.openrouter_model_2}) — clé {flag(self.llm.openrouter_api_key)}",
            f"                    4. Gemini ({self.llm.gemini_model}) — clé {flag(self.llm.gemini_api_key)}",
            f"  Recherche       : DuckDuckGo (sans clé) + Tavily {flag(self.search.tavily_api_key)}",
            f"  Telegram        : {'✅ configuré' if self.telegram.is_configured else '❌ non configuré'}",
            f"  Search Console  : {'✅ configuré' if self.search_console.is_configured else '❌ non configuré (repli : export manuel)'}",
            f"  Validation      : HUMAN_REVIEW={self.human_review}",
            f"  Orchestrateur   : {self.orchestrator}",
            f"  Dossier blog    : {self.publishing.blog_content_dir}",
            f"  Dépôt blog      : {self.publishing.blog_repo_dir}",
            f"  Stockage        : {self.storage.root}",
        ])
