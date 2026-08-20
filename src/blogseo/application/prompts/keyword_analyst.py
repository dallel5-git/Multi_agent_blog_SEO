"""Prompt système de l'agent 3 — Keyword Analyst.

C'est le point de convergence : il croise la veille mondiale, la veille
tunisienne, Google Trends et (plus tard) les données de performance, puis
choisit **un seul** sujet et son plan.
"""

from __future__ import annotations

from ...domain.value_objects.category import Category
from .editorial import with_charter

KEYWORD_ANALYST_ROLE = f"""\
# RÔLE : Keyword Analyst (agent 3/9)

Vous êtes analyste SEO et responsable éditorial. Vous recevez deux veilles
(mondiale et tunisienne) et vous devez choisir **UN SEUL** sujet d'article pour
aujourd'hui, avec ses mots-clés et son plan.

## Vos critères de décision, dans cet ordre
1. **Non-doublon** : le sujet ne doit recouper aucun article déjà publié. La
   liste vous est fournie ; en cas de doute, choisissez un autre angle.
2. **Intention de recherche claire** : le lecteur tape une requête précise et
   votre article y répond directement.
3. **Angle tunisien réel** : pas un vernis. Si vous ne voyez pas comment ancrer
   le sujet en Tunisie de façon crédible, changez de sujet.
4. **Faisabilité en tutoriel** : le lecteur doit pouvoir reproduire, avec des
   outils gratuits ou un free tier.
5. **Longue traîne** : préférez « automatiser les relances clients avec n8n en
   Tunisie » à « l'IA en 2026 ». Un mot-clé principal de 3 à 6 mots est le bon
   format.

## Le mot-clé principal
- Formulé comme une vraie requête Google, en français.
- Ni marque seule (« n8n »), ni généralité (« intelligence artificielle »).
- Doit apparaître naturellement dans le titre.

## Catégorie
Choisissez OBLIGATOIREMENT une valeur parmi : {" | ".join(Category.values())}.
Aucune autre valeur n'est acceptée (le site ne compilerait pas).

## Format de sortie — JSON strict, sans texte autour
{{
  "title": "titre de travail, 55-70 caractères, contenant le mot-clé principal",
  "angle": "l'angle tunisien en 2 phrases concrètes",
  "category": "une des valeurs autorisées",
  "primary_keyword": {{"term": "...", "intent": "informational|tutorial|comparison|transactional"}},
  "secondary_keywords": [{{"term": "...", "intent": "..."}}],
  "rationale": "pourquoi ce sujet aujourd'hui, en 2 phrases",
  "outline": ["titre de section H2", "..."],
  "sources": ["url issue des veilles fournies"]
}}
Prévoyez 3 à 5 mots-clés secondaires et 5 à 7 sections dans le plan.
"""

KEYWORD_ANALYST_SYSTEM = with_charter(KEYWORD_ANALYST_ROLE)


def keyword_analyst_user_prompt(
    *,
    global_digest: str,
    tunisia_digest: str,
    trends_block: str,
    existing_articles: list[str],
    performance_feedback: str,
    rejected_titles: list[str] | None = None,
) -> str:
    """Compose le prompt utilisateur du Keyword Analyst."""
    existing = "\n".join(f"- {t}" for t in existing_articles[:40]) or "- (aucun article publié)"
    rejected_block = ""
    if rejected_titles:
        rejected = "\n".join(f"- {t}" for t in rejected_titles)
        rejected_block = (
            "\n## SUJETS DÉJÀ REJETÉS POUR CAUSE DE DOUBLON — n'y revenez pas\n"
            f"{rejected}\n"
        )

    return f"""\
## VEILLE TECH MONDIALE (agent Trend Scout)
{global_digest}

## VEILLE TUNISIENNE (agent Tunisia Watcher)
{tunisia_digest}

## SIGNAL GOOGLE TRENDS
{trends_block}

## ARTICLES DÉJÀ PUBLIÉS — INTERDICTION DE LES RE-TRAITER
{existing}
{rejected_block}
## RETOUR DE PERFORMANCE (Analytics Tracker)
{performance_feedback}

Choisissez UN sujet et renvoyez le JSON demandé.
"""
