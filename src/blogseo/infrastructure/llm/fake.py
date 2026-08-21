"""Adapter LLM factice, pour `--dry-run --offline` et les tests unitaires.

Permet de dérouler tout le pipeline (9 agents, boucle de feedback, écriture du
`.mdx`) sans aucune clé d'API et sans réseau. C'est le mode recommandé pour
valider l'installation avant de configurer Cerebras/Groq.
"""

from __future__ import annotations

import json
import logging
import re

from ...domain.ports.llm import LLMPort, LLMResponse

logger = logging.getLogger(__name__)

_LOREM_SECTION = (
    "Concrètement, cette approche change la donne pour une PME tunisienne : au lieu de "
    "mobiliser une demi-journée par semaine sur une tâche répétitive, le workflow tourne "
    "seul et le gain se mesure directement en dinars économisés. Voici comment procéder "
    "étape par étape, avec les points de vigilance rencontrés sur le terrain à Tunis.\n\n"
    "```python\n"
    "# Exemple minimal, à adapter à votre contexte\n"
    "def run_workflow(payload: dict) -> dict:\n"
    '    """Traite une entrée et renvoie le résultat normalisé."""\n'
    "    return {\"status\": \"ok\", \"payload\": payload}\n"
    "```\n\n"
    "Le principal écueil est de vouloir tout automatiser d'un coup. Commencez par un seul "
    "processus, mesurez, puis étendez. C'est la méthode qui fonctionne le mieux auprès des "
    "équipes que j'accompagne, qu'il s'agisse d'étudiants ou de petites structures."
)


class FakeLLM(LLMPort):
    """Renvoie des réponses plausibles et déterministes, sans réseau."""

    name = "fake"

    def __init__(self, *, article_words: int = 1400) -> None:
        self.article_words = article_words
        self.calls: list[tuple[str, str]] = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        self.calls.append((system_prompt[:80], user_prompt[:80]))
        text = self._respond(system_prompt, user_prompt, json_mode)
        logger.debug("[fake-llm] réponse de %s caractères", len(text))
        return LLMResponse(text=text, provider=self.name, model="fake-1", latency_s=0.0)

    # ------------------------------------------------------------------ #
    def _respond(self, system_prompt: str, user_prompt: str, json_mode: bool) -> str:
        role = system_prompt.lower()

        if "planification d'une série" in role:
            match = re.search(r"NOMBRE D'ARTICLES ATTENDU\n(\d+)", user_prompt)
            size = int(match.group(1)) if match else 3
            topics = [
                {
                    "title": f"Sujet {i} de la série (exemple hors ligne)",
                    "angle": "Angle tunisien concret, exemple généré hors ligne.",
                    "category": "n8n",
                    "primary_keyword": f"mot-clé exemple {i}",
                    "secondary_keywords": ["mot-clé secondaire"],
                    "outline": ["Introduction", "Mise en place", "Conclusion"],
                    "rationale": "Exemple généré par le LLM factice (mode hors ligne).",
                }
                for i in range(1, size + 1)
            ]
            return json.dumps(
                {"series_title": "Série d'exemple (LLM factice)", "topics": topics}, ensure_ascii=False
            )

        if "keyword analyst" in role or "analyste seo" in role:
            return json.dumps({
                "title": "Automatiser sa prospection avec n8n : le guide pour les PME tunisiennes",
                "angle": "Adapté au contexte tunisien : budget en dinars, outils gratuits, "
                         "et contraintes des petites structures de Tunis et Sfax.",
                "category": "n8n",
                "primary_keyword": {"term": "automatiser prospection n8n", "intent": "tutorial"},
                "secondary_keywords": [
                    {"term": "n8n Tunisie", "intent": "informational"},
                    {"term": "automatisation PME tunisienne", "intent": "informational"},
                    {"term": "workflow gratuit n8n", "intent": "tutorial"},
                ],
                "rationale": "Sujet porteur : forte demande locale et aucun article équivalent publié.",
                "outline": [
                    "Pourquoi la prospection manuelle coûte cher aux PME tunisiennes",
                    "Installer n8n gratuitement (self-hosted vs cloud)",
                    "Construire le workflow pas à pas",
                    "Brancher une source de leads locale",
                    "Mesurer le gain de temps et les limites",
                ],
                "sources": ["https://news.ycombinator.com", "https://n8n.io/blog"],
            }, ensure_ascii=False)

        if "seo editor" in role or "éditeur seo" in role:
            return json.dumps({
                "meta_title": "Automatiser sa prospection avec n8n en Tunisie",
                "meta_description": (
                    "Guide pratique pour automatiser votre prospection commerciale avec n8n, "
                    "pensé pour les PME et freelances tunisiens : installation gratuite, "
                    "workflow complet et gains mesurés."
                ),
                "slug": "automatiser-prospection-n8n-pme-tunisiennes",
                "focus_keyword": "automatiser prospection n8n",
                "secondary_keywords": ["n8n Tunisie", "automatisation PME tunisienne"],
                "cover_alt_text": "Workflow n8n d'automatisation de prospection sur un écran d'ordinateur",
                "internal_links": ["automatiser-workflows-n8n", "make-vs-n8n-comparatif"],
                "tags": ["n8n", "automatisation", "pme", "tunisie"],
            }, ensure_ascii=False)

        if "technical reviewer" in role or "relecteur technique" in role:
            return json.dumps({"findings": [], "notes": "Aucune erreur technique bloquante détectée."},
                              ensure_ascii=False)

        if "content writer" in role or "rédacteur" in role:
            return self._fake_article()

        if json_mode:
            return "{}"
        return "Réponse simulée par le fournisseur LLM factice (mode hors ligne)."

    def _fake_article(self) -> str:
        intro = (
            "Vous passez encore vos matinées à recopier des contacts d'un fichier Excel vers "
            "votre boîte mail ? En Tunisie, où les petites équipes jonglent avec des budgets "
            "serrés, ce temps perdu se paie cash. Dans ce guide, on construit ensemble un "
            "workflow **n8n** qui fait le travail à votre place, entièrement avec des outils "
            "gratuits.\n"
        )
        sections = [
            "## Pourquoi la prospection manuelle coûte cher aux PME tunisiennes",
            "## Installer n8n gratuitement",
            "## Construire le workflow pas à pas",
            "## Brancher une source de leads locale",
            "## Mesurer le gain de temps et les limites",
        ]
        body = [intro]
        for heading in sections:
            body.append(heading)
            body.append(_LOREM_SECTION)
        body.append(
            "## Pour aller plus loin\n\n"
            "Je détaille ce workflow en vidéo sur ma chaîne YouTube, avec le fichier JSON "
            "prêt à importer : [chaîne YouTube](https://www.youtube.com/@oussamadallel5). "
            "Si vous voulez d'autres tutoriels de ce type, dites-le moi en commentaire."
        )
        article = "\n\n".join(body)

        # On rallonge jusqu'à dépasser le minimum de mots exigé par le Quality Gate.
        # Le comptage exclut les blocs de code, exactement comme `Article.word_count`.
        def countable(text: str) -> int:
            return len(re.sub(r"```.*?```", " ", text, flags=re.DOTALL).split())

        while countable(article) < self.article_words:
            article += "\n\n" + _LOREM_SECTION
        return article
