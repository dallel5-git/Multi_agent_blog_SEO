"""Agent 2/9 — Tunisia Watcher : veille locale tunisienne.

Trois sources combinées :
1. recherche web ciblée (DuckDuckGo, repli Tavily) sur des requêtes tunisiennes ;
2. flux RSS de médias tech tunisiens, si l'auteur en configure dans `.env` ;
3. Google Trends géolocalisé TN, pour pondérer les mots-clés.

Le LLM ne sert qu'à structurer : il n'a pas le droit d'inventer un fait local.
"""

from __future__ import annotations

from ...domain.entities.trend import TrendDigest, TrendItem, TrendOrigin
from ...domain.ports.llm import LLMPort
from ...domain.ports.search import SearchPort, TechSourcePort, TrendsPort
from ...shared.json_utils import extract_json
from ...shared.retry import safe_call
from ..dto.pipeline_state import PipelineState
from ..prompts.scouting import TUNISIA_WATCHER_SYSTEM, tunisia_watcher_user_prompt
from .base import Agent

#: Mots-clés dont on mesure l'intérêt en Tunisie (Google Trends, geo=TN).
DEFAULT_TREND_KEYWORDS = [
    "intelligence artificielle", "automatisation", "n8n", "chatgpt", "python",
]


class TunisiaWatcherAgent(Agent):
    """Veille sur l'écosystème tech et business tunisien."""

    name = "tunisia_watcher"
    label = "Tunisia Watcher — veille tunisienne"
    critical = False

    def __init__(
        self,
        search: SearchPort,
        trends: TrendsPort,
        llm: LLMPort,
        *,
        queries: tuple[str, ...] | list[str],
        rss_source: TechSourcePort | None = None,
        trend_keywords: list[str] | None = None,
        max_results: int = 6,
    ) -> None:
        super().__init__()
        self.search = search
        self.trends = trends
        self.llm = llm
        self.queries = list(queries)
        self.rss_source = rss_source
        self.trend_keywords = trend_keywords or DEFAULT_TREND_KEYWORDS
        self.max_results = max_results

    def run(self, state: PipelineState) -> PipelineState:
        digest = TrendDigest(origin=TrendOrigin.TUNISIA)

        # 1. Recherche web ciblée Tunisie.
        for query in self.queries:
            results = safe_call(
                self.search.search, query,
                max_results=self.max_results, region="fr-tn",
                default=[], label=f"recherche « {query} »",
            ) or []
            for result in results:
                digest.items.append(
                    TrendItem(
                        title=result.title,
                        url=result.url,
                        source=result.source or "recherche web",
                        origin=TrendOrigin.TUNISIA,
                        summary=result.snippet,
                        keywords=(query,),
                    )
                )

        # 2. Flux RSS tunisiens optionnels.
        if self.rss_source is not None:
            items = safe_call(self.rss_source.fetch, default=[], label="RSS Tunisie") or []
            digest.items.extend(items)

        state.tunisia_digest = digest
        self.logger.info("%s signal(aux) tunisien(s) collecté(s)", len(digest))

        # 3. Google Trends (géo TN) — signal facultatif, jamais bloquant.
        scores = safe_call(
            self.trends.interest_over_time, self.trend_keywords,
            geo="TN", timeframe="today 3-m",
            default={}, label="Google Trends TN",
        ) or {}
        state.trends_scores = scores

        if not digest.items and not scores:
            state.warn("Veille tunisienne vide : recherche web et Trends indisponibles")
            return state

        # 4. Structuration par le LLM.
        trends_block = (
            "\n".join(f"- {term} : intérêt moyen {score}" for term, score in sorted(
                scores.items(), key=lambda kv: kv[1], reverse=True))
            or "(aucune donnée Google Trends)"
        )
        response = self.llm.generate(
            TUNISIA_WATCHER_SYSTEM,
            tunisia_watcher_user_prompt(digest.as_context_block(limit=25), trends_block),
            temperature=0.3,
            json_mode=True,
        )
        state.tunisia_context = extract_json(
            response.text,
            default={"local_context": [], "pain_points": [], "angles": [], "coverage_gap": ""},
        )

        gap = state.tunisia_context.get("coverage_gap")
        if gap:
            self.logger.warning("Angle mort de la veille tunisienne : %s", gap)
        self.logger.info(
            "%s fait(s) local(aux), %s angle(s) éditorial(aux)",
            len(state.tunisia_context.get("local_context", [])),
            len(state.tunisia_context.get("angles", [])),
        )
        return state

    def describe(self, state: PipelineState) -> str:
        signals = len(state.tunisia_digest) if state.tunisia_digest else 0
        angles = len(state.tunisia_context.get("angles", []))
        return f"{signals} signaux locaux → {angles} angles"
