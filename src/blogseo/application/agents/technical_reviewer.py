"""Agent 5/9 — Technical Reviewer : exactitude technique.

Deux couches complémentaires :
1. **Déterministe** : vérification HTTP réelle des liens cités et détection de
   secrets en clair — pas de LLM, donc pas d'hallucination possible.
2. **LLM** : relecture du code et des affirmations factuelles.

Non critique : si la relecture échoue, on publie quand même avec un
avertissement plutôt que de perdre l'article.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import requests

from ...domain.entities.review import FindingKind, ReviewFinding, ReviewResult
from ...domain.ports.llm import LLMPort
from ...shared.json_utils import extract_json
from ...shared.text import extract_urls
from ..dto.pipeline_state import PipelineState
from ..prompts.reviewing import TECHNICAL_REVIEWER_SYSTEM, technical_reviewer_user_prompt
from .base import Agent

#: Motifs de secrets à ne jamais laisser passer dans un article public.
_SECRET_PATTERNS = (
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "clé Google API"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "clé de type OpenAI"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "clé Groq"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "token GitHub"),
    (re.compile(r"\b\d{9,10}:[A-Za-z0-9_\-]{35}\b"), "token de bot Telegram"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "token Slack"),
)


class TechnicalReviewerAgent(Agent):
    """Relecture technique de l'article."""

    name = "technical_reviewer"
    label = "Technical Reviewer — exactitude technique"
    critical = False

    def __init__(
        self,
        llm: LLMPort,
        *,
        check_links: bool = True,
        link_timeout_s: int = 10,
        max_links: int = 15,
        temperature: float = 0.2,
    ) -> None:
        super().__init__()
        self.llm = llm
        self.check_links = check_links
        self.link_timeout_s = link_timeout_s
        self.max_links = max_links
        self.temperature = temperature

    def run(self, state: PipelineState) -> PipelineState:
        article = state.article
        if article is None:
            raise ValueError("Aucun article à relire")

        result = ReviewResult()

        # 1. Vérification déterministe des liens.
        if self.check_links:
            result.checked_urls = self._check_links(extract_urls(article.body_markdown))
            if result.broken_urls:
                self.logger.warning("%s lien(s) mort(s) détecté(s)", len(result.broken_urls))

        # 2. Détection déterministe de secrets.
        for pattern, label in _SECRET_PATTERNS:
            for match in pattern.finditer(article.body_markdown):
                result.findings.append(
                    ReviewFinding(
                        kind=FindingKind.CODE_ERROR,
                        excerpt=match.group(0)[:12] + "…",
                        problem=f"Un secret ressemblant à une {label} apparaît en clair dans l'article",
                        suggestion="Remplacer par une variable d'environnement, ex. os.getenv(\"API_KEY\")",
                        blocking=True,
                    )
                )

        # 3. Relecture par le LLM.
        link_report = self._format_link_report(result)
        response = self.llm.generate(
            TECHNICAL_REVIEWER_SYSTEM,
            technical_reviewer_user_prompt(
                article_markdown=article.body_markdown,
                research_context=state.research_context or "(non disponible)",
                link_report=link_report,
            ),
            temperature=self.temperature,
            json_mode=True,
        )
        payload = extract_json(response.text, default={"findings": [], "notes": ""})
        result.notes = str(payload.get("notes", ""))

        for raw in payload.get("findings") or []:
            if not isinstance(raw, dict) or not raw.get("problem"):
                continue
            try:
                kind = FindingKind(str(raw.get("kind", "factual_error")))
            except ValueError:
                kind = FindingKind.FACTUAL_ERROR
            result.findings.append(
                ReviewFinding(
                    kind=kind,
                    excerpt=str(raw.get("excerpt", ""))[:200],
                    problem=str(raw.get("problem", "")),
                    suggestion=str(raw.get("suggestion", "")),
                    blocking=bool(raw.get("blocking", False)),
                )
            )

        state.review = result
        self.logger.info(
            "Relecture : %s remarque(s) dont %s bloquante(s), %s lien(s) mort(s)",
            len(result.findings), len(result.blocking_findings), len(result.broken_urls),
        )
        return state

    # ------------------------------------------------------------------ #
    def _check_links(self, urls: list[str]) -> dict[str, bool]:
        """Teste chaque URL en HEAD puis en GET, en parallèle."""
        urls = urls[: self.max_links]
        if not urls:
            return {}

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; blogseo-linkcheck/1.0)"})

        def probe(url: str) -> tuple[str, bool]:
            # On compare `method_name`, pas l'objet méthode : une méthode liée
            # (`session.head`) est recréée à chaque accès et n'est jamais `is`
            # identique à elle-même d'un accès à l'autre, même pour le même appel.
            for method_name in ("head", "get"):
                method = getattr(session, method_name)
                try:
                    response = method(url, timeout=self.link_timeout_s, allow_redirects=True)
                    if response.status_code < 400:
                        return url, True
                    # Beaucoup de sites refusent HEAD : on retente en GET.
                    if method_name == "head" and response.status_code in (403, 405, 501):
                        continue
                    return url, False
                except requests.RequestException:
                    continue
            return url, False

        with ThreadPoolExecutor(max_workers=6) as pool:
            return dict(pool.map(probe, urls))

    @staticmethod
    def _format_link_report(result: ReviewResult) -> str:
        if not result.checked_urls:
            return "(aucun lien externe dans l'article)"
        lines = [f"- {'OK ' if ok else 'MORT'} {url}" for url, ok in result.checked_urls.items()]
        return "\n".join(lines)

    def describe(self, state: PipelineState) -> str:
        if not state.review:
            return "non relu"
        return (
            f"{len(state.review.findings)} remarque(s), "
            f"{len(state.review.blocking_findings)} bloquante(s), "
            f"{len(state.review.broken_urls)} lien(s) mort(s)"
        )
