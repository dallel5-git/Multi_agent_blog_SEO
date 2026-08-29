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
from pilotage.brand_kernel.schema import (  # noqa: E402
    Audience,
    BrandKernel,
    Colors,
    Fonts,
    Handles,
    Identity,
    Logo,
    Tracking,
    Visual,
    Voice,
)
from pilotage.platforms import Platform  # noqa: E402
from pilotage.shared_calendar.migrate import SCHEMA_SQL_PATH  # noqa: E402
from pilotage.shared_calendar.repository import CalendarRepository  # noqa: E402

BODY_TEMPLATE = """\
Vous perdez encore des heures chaque semaine à relancer vos contacts à la main ?
En Tunisie, où les équipes sont petites et les budgets serrés, ce temps compte double.
Ce guide montre comment gérer sa prospection avec n8n sans dépenser un dinar.

## Pourquoi la prospection avec n8n change la donne en Tunisie

{filler}

## Installer n8n gratuitement

{filler}

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


@pytest.fixture
def brand_kernel() -> BrandKernel:
    """Brand Kernel synthétique et complet, pour les tests de `pilotage`.

    Ne lit jamais le vrai `brand_kernel.yaml` du dépôt (qui peut encore
    porter des `TODO`, ou changer) : construit directement les dataclasses,
    sur le modèle de `tests/unit/test_brand_kernel.py::_kernel_data`.
    """
    return BrandKernel(
        version=1,
        identity=Identity(
            name="Oussama Dallel",
            slogan="Prenez le contrôle de votre temps grâce à l'IA",
            baseline="Tutoriels concrets sur l'IA et l'automatisation pour reprendre le contrôle de ton temps.",
            language="fr",
            handles=Handles(
                youtube="https://www.youtube.com/@oussamadallel5",
                linkedin=None, github=None, blog="https://exemple.test",
                tiktok=None, instagram=None, x=None, facebook=None, telegram_channel=None,
            ),
        ),
        voice=Voice(
            tone=("direct", "pragmatique", "inspirant", "accessible"),
            address="tu",
            forbidden=("promesses de revenus chiffrées",),
            signature_phrases=("Passe à l'action, pas seulement à la lecture.",),
            emoji_policy="parcimonieux",
        ),
        visual=Visual(
            colors=Colors(primary="#9333EA", secondary="#2E1065", accent="#22D3EE",
                           background="#0B0712", text="#F5F3FF"),
            logo=Logo(path="assets/brand/logo-wordmark.svg", safe_zone_ratio=0.1),
            fonts=Fonts(heading="Poppins", body="Inter"),
            thumbnail_style="Dégradé violet à indigo sur fond sombre, titre blanc en gras.",
        ),
        audience=Audience(
            country="Tunisie",
            segments=("étudiants", "PME et petits business", "professionnels IT", "développeurs"),
            technical_level_by_platform=dict.fromkeys(Platform.piloted(), "mixte"),
            pain_points=("manque de temps", "peur de la complexité technique"),
            currency="TND",
        ),
        offers=(),
        tracking=Tracking(param="ref", scheme="od-{platform}"),
    )


@pytest.fixture
def calendar_repository() -> CalendarRepository:
    """`CalendarRepository` en mémoire, schéma appliqué — pour les tests `pilotage`."""
    repo = CalendarRepository(":memory:")
    repo._connection.executescript(SCHEMA_SQL_PATH.read_text(encoding="utf-8"))
    yield repo
    repo.close()
