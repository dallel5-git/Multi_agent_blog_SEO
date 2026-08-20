"""Agent 1/9 — Trend Scout : veille tech mondiale.

Collecte des signaux réels via les sources publiques gratuites (Hacker News,
Reddit, dev.to, RSS Product Hunt / n8n), puis demande au LLM de les regrouper en
thèmes exploitables. Non critique : si toutes les sources tombent, le pipeline
continue avec la seule veille tunisienne.
"""

from __future__ import annotations

from ...domain.entities.trend import TrendDigest, TrendOrigin
from ...domain.ports.llm import LLMPort
from ...domain.ports.search import TechSourcePort
from ...shared.json_utils import extract_json
from ...shared.retry import safe_call
from ..dto.pipeline_state import PipelineState
from ..prompts.scouting import TREND_SCOUT_SYSTEM, trend_scout_user_prompt
from .base import Agent


class TrendScoutAgent(Agent):
    """Veille technologique mondiale."""

    name = "trend_scout"
    label = "Trend Scout — veille tech mondiale"
    critical = False  # une veille vide ne doit pas casser le run

    def __init__(self, sources: list[TechSourcePort], llm: LLMPort, *, per_source_limit: int = 15) -> None:
        super().__init__()
        self.sources = sources
        self.llm = llm
        self.per_source_limit = per_source_limit

    def run(self, state: PipelineState) -> PipelineState:
        digest = TrendDigest(origin=TrendOrigin.GLOBAL_TECH)

        # 1. Collecte : chaque source est isolée, une panne n'affecte pas les autres.
        for source in self.sources:
            items = safe_call(source.fetch, limit=self.per_source_limit, default=[], label=source.name)
            if items:
                digest.items.extend(items)
            else:
                digest.errors.append(f"{source.name} : aucun signal")
                self.logger.warning("Source sans résultat : %s", source.name)

        state.global_digest = digest
        self.logger.info("%s signal(aux) collecté(s) sur %s source(s)", len(digest), len(self.sources))

        if not digest.items:
            state.warn("Veille mondiale vide : toutes les sources sont indisponibles")
            return state

        # 2. Synthèse par le LLM en thèmes hiérarchisés.
        response = self.llm.generate(
            TREND_SCOUT_SYSTEM,
            trend_scout_user_prompt(digest.as_context_block(limit=30), state.existing_titles),
            temperature=0.3,
            json_mode=True,
        )
        payload = extract_json(response.text, default={"themes": []})
        themes = payload.get("themes", [])
        state.global_themes = [t for t in themes if isinstance(t, dict) and t.get("theme")]

        self.logger.info("%s thème(s) mondial(aux) retenu(s)", len(state.global_themes))
        for theme in state.global_themes[:5]:
            self.logger.debug(
                "  • %s (tutoriel=%s, tunisie=%s)",
                theme.get("theme"), theme.get("tutorial_potential"), theme.get("tunisia_fit"),
            )
        return state

    def describe(self, state: PipelineState) -> str:
        signals = len(state.global_digest) if state.global_digest else 0
        return f"{signals} signaux → {len(state.global_themes)} thèmes"
