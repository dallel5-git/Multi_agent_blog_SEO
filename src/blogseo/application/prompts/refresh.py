"""Prompt du refresh ciblé (issue #42) : régénérer titre/description d'un
article sous-performant, sans toucher au corps.
"""

from __future__ import annotations

from ...domain.value_objects.seo_metadata import (
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    TITLE_MAX,
    TITLE_MIN,
)
from .editorial import with_charter

REFRESH_ROLE = f"""\
# RÔLE : Refresh SEO ciblé (régénération d'un article sous-performant)

Un article déjà publié génère beaucoup d'impressions Google mais très peu de
clics : son contenu est bon (il ressort dans les résultats de recherche),
mais son titre et sa description n'incitent pas au clic, ou ne correspondent
plus aux requêtes qui l'affichent. Vous NE réécrivez PAS le contenu : vous
proposez uniquement un nouveau titre et une nouvelle description.

## Ce que vous produisez
- **meta_title** : {TITLE_MIN} à {TITLE_MAX} caractères, contient le mot-clé
  principal, formule une promesse concrète plus incitative que le titre
  actuel. Pas de bourrage de mots-clés, pas de clickbait trompeur (le contenu
  ne change pas : le titre doit rester fidèle à ce qui est réellement dedans).
- **meta_description** : {DESCRIPTION_MIN} à {DESCRIPTION_MAX} caractères,
  reformule le bénéfice de façon plus concrète, contient le mot-clé principal.

## Ce que vous ne faites pas
- Vous ne modifiez pas le corps de l'article.
- Vous ne changez pas le sujet ni l'angle : vous rendez le même contenu plus
  attractif dans les résultats de recherche.

## Signal à exploiter en priorité
Si des requêtes réelles (impressions Google) sont fournies, elles indiquent
ce que les internautes tapent pour tomber sur cet article sans cliquer :
alignez le titre/la description sur ces requêtes plutôt que d'inventer un
nouvel angle.

## Format de sortie — JSON strict, sans texte autour
{{
  "meta_title": "...",
  "meta_description": "..."
}}
"""

REFRESH_SYSTEM = with_charter(REFRESH_ROLE)


def refresh_user_prompt(
    *,
    current_title: str,
    current_description: str,
    category: str,
    article_excerpt: str,
    focus_keyword: str,
    top_queries: list[str],
    impressions: int,
    clicks: int,
    ctr: float,
    feedback: str = "",
) -> str:
    queries = "\n".join(f"- {q}" for q in top_queries) or "(aucune donnée de requête disponible)"
    stats = (
        f"{impressions} impressions, {clicks} clics, CTR {ctr:.2%}"
        if impressions
        else "(aucune donnée de performance disponible — jugez uniquement sur le contenu)"
    )
    retry = f"\n## RETOUR SUR LA PROPOSITION PRÉCÉDENTE\n{feedback}\n" if feedback else ""

    return f"""\
## TITRE ACTUEL
{current_title}

## DESCRIPTION ACTUELLE
{current_description}

## CATÉGORIE
{category}

## MOT-CLÉ PRINCIPAL (estimé)
{focus_keyword or "(non identifié — déduisez-le du titre et du contenu)"}

## STATISTIQUES DE PERFORMANCE (28 derniers jours)
{stats}

## REQUÊTES RÉELLES QUI AFFICHENT CET ARTICLE SANS CLIC
{queries}

## DÉBUT DE L'ARTICLE (pour rester fidèle au contenu)
{article_excerpt}
{retry}
Renvoyez le JSON demandé.
"""
