"""Tests du filtre de pertinence de la veille partagée (`pilotage.shared.trend_sources`).

Bug réel constaté en conditions réelles : un simple test de sous-chaîne fait
matcher `"ai"` à l'intérieur de `"paint"` et `"main"` (un signal Hacker News
sur MS Paint est passé le filtre à cause du mot « paint » dans le titre et
de « main/ » dans l'URL). `_is_relevant()` doit matcher des MOTS entiers.
"""

from __future__ import annotations

from pilotage.shared.trend_sources import _is_relevant, collect_trends


def test_is_relevant_ne_matche_pas_ai_a_linterieur_dun_mot():
    assert _is_relevant("MS Paint and Photos invisibly watermark", "https://exemple.test/main/") is False


def test_is_relevant_matche_ai_comme_mot_entier():
    assert _is_relevant("Building an AI agent from scratch") is True


def test_is_relevant_matche_les_termes_a_tiret_comme_mots_entiers():
    assert _is_relevant("Le mouvement no-code explose en 2026") is True


def test_is_relevant_matche_dans_lurl_si_absent_du_titre():
    assert _is_relevant("Un nouvel outil sorti cette semaine", "https://exemple.test/n8n-guide") is True


def test_is_relevant_insensible_a_la_casse():
    assert _is_relevant("Un nouveau LLM open source") is True


def test_is_relevant_refuse_un_titre_hors_sujet():
    assert _is_relevant("Where did all the public bathrooms go?") is False


def test_collect_trends_hors_ligne_ne_fait_aucun_appel_reseau():
    assert collect_trends(offline=True) == []
