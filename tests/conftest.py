"""Fixtures partagées par les tests."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from blogseo.domain.entities.article import Article  # noqa: E402
from blogseo.domain.value_objects.category import Category  # noqa: E402
from blogseo.domain.value_objects.seo_metadata import SeoMetadata  # noqa: E402
from blogseo.domain.value_objects.slug import Slug  # noqa: E402

BODY_TEMPLATE = """\
Vous perdez encore des heures chaque semaine à relancer vos contacts à la main ?
En Tunisie, où les équipes sont petites et les budgets serrés, ce temps compte double.
Ce guide montre comment gérer sa prospection avec n8n sans dépenser un dinar.

## Pourquoi la prospection avec n8n change la donne en Tunisie

{filler}

## Installer n8n gratuitement

{filler}

```python
# Exemple minimal commenté en français
def run() -> str:
    return "ok"
```

## Construire le workflow de prospection

{filler}

- première étape
- deuxième étape

## Mesurer le gain en dinars

{filler}

## Pour aller plus loin

Retrouvez le tutoriel complet sur ma chaîne YouTube.
"""

FILLER = (
    "Le principe est simple : on identifie une tâche répétitive, on la découpe en "
    "étapes claires, puis on la confie à un workflow automatisé. À Tunis comme à Sfax, "
    "les gains se mesurent très vite, souvent dès la première semaine d'utilisation. "
)


def make_body(word_target: int = 1400) -> str:
    """Génère un corps d'article réaliste d'au moins `word_target` mots."""
    filler = FILLER
    while len(BODY_TEMPLATE.format(filler=filler).split()) < word_target:
        filler += FILLER
    return BODY_TEMPLATE.format(filler=filler)


@pytest.fixture
def seo() -> SeoMetadata:
    return SeoMetadata(
        meta_title="Automatiser sa prospection avec n8n en Tunisie",
        meta_description=(
            "Guide pratique pour gérer sa prospection avec n8n, pensé pour les PME et "
            "freelances tunisiens : installation gratuite et workflow complet."
        ),
        focus_keyword="prospection avec n8n",
        secondary_keywords=("n8n Tunisie",),
    )


@pytest.fixture
def article(seo: SeoMetadata) -> Article:
    return Article(
        title="Automatiser sa prospection avec n8n",
        slug=Slug("automatiser-prospection-n8n"),
        body_markdown=make_body(),
        seo=seo,
        category=Category.N8N,
        tags=("n8n", "automatisation", "tunisie"),
        published_on=date(2026, 8, 19),
    )
