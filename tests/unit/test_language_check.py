"""Tests du contrôle de langue : l'article DOIT être en français."""

from __future__ import annotations

import pytest

from blogseo.application.agents.quality_gate import QualityGateAgent
from blogseo.application.dto.pipeline_state import PipelineState
from blogseo.domain.entities.pipeline_run import PipelineRun

TEXTE_ANGLAIS = """\
## Why you should automate your workflow

The main reason you want to automate your business processes is that they are
repetitive and they will cost you a lot of time. Here is what you can do with
this tool and how it will help your team to be more productive every day.

## What you will learn here

You will learn how to build the workflow from scratch, and what the best
practices are when you want to scale it for your company and your clients.
"""

TEXTE_FRANCAIS = """\
## Pourquoi automatiser vos workflows en Tunisie

La raison principale pour laquelle vous voulez automatiser vos processus est
qu'ils sont répétitifs et qu'ils vous coûtent beaucoup de temps. Voici ce que
vous pouvez faire avec cet outil et comment il aidera votre équipe à Tunis.

## Ce que vous allez apprendre

Vous allez apprendre à construire le workflow depuis le début, et quelles sont
les bonnes pratiques quand vous voulez le déployer dans votre entreprise.
"""


@pytest.fixture
def gate() -> QualityGateAgent:
    return QualityGateAgent()


def run_language_check(gate, article, body: str):
    article.body_markdown = body
    state = PipelineState(run=PipelineRun())
    state.article = article
    state.iteration = 1
    gate.run(state)
    return {c.name: c for c in state.quality.checks}


class TestDetectionDeLangue:
    def test_un_article_francais_passe(self, gate, article):
        checks = run_language_check(gate, article, TEXTE_FRANCAIS)
        assert checks["langue_francaise"].passed

    def test_un_article_anglais_est_bloque(self, gate, article):
        checks = run_language_check(gate, article, TEXTE_ANGLAIS)
        assert not checks["langue_francaise"].passed
        assert checks["langue_francaise"].severity.value == "blocker"
        assert "FRANÇAIS" in checks["langue_francaise"].message

    def test_l_article_de_reference_est_francais(self, gate, article):
        checks = run_language_check(gate, article, article.body_markdown)
        assert checks["langue_francaise"].passed

    def test_titres_en_anglais_declenchent_un_avertissement(self, gate, article):
        body = TEXTE_FRANCAIS + "\n\n## What you should know about this tool\n\nDu texte français ici."
        checks = run_language_check(gate, article, body)
        assert not checks["titres_en_francais"].passed

    def test_les_noms_d_outils_anglais_sont_tolérés(self, gate, article):
        body = TEXTE_FRANCAIS.replace("cet outil", "n8n, Make et LangChain")
        checks = run_language_check(gate, article, body)
        assert checks["langue_francaise"].passed

    def test_le_code_anglais_n_influence_pas_la_detection(self, gate, article):
        body = TEXTE_FRANCAIS + "\n\n```python\n" + "the and you your with this that for\n" * 30 + "```\n"
        checks = run_language_check(gate, article, body)
        assert checks["langue_francaise"].passed

    def test_texte_trop_court_est_bloque(self, gate, article):
        checks = run_language_check(gate, article, "## Court\n\nTrois mots.")
        assert not checks["langue_francaise"].passed
