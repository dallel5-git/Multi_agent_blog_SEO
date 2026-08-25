"""Contrat commun des pipelines de plateforme.

`PlatformPipeline`, dans l'esprit de `blogseo.application.agents.base.Agent` :
chronométrage, trace, et distinction entre étape critique et étape
dégradable. Deux règles héritées de l'existant :

1. un pipeline n'en connaît jamais un autre — chaque sous-classe importe
   uniquement `pilotage.pipelines.base`, jamais un module d'une autre
   plateforme ;
2. une source de veille morte dégrade le run, elle ne le fait jamais échouer
   — `watch()` est la seule étape non critique.

`watch()`, `choose_topic()` et `write()` sont abstraites : c'est tout ce
qu'une plateforme doit fournir. `submit()` est concrète ici — enregistrer un
brouillon en base est un geste identique quelle que soit la plateforme, le
dupliquer dans chaque sous-classe violerait « ajouter un pipeline = créer une
sous-classe, rien d'autre à modifier ».
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..brand_kernel.loader import load_brand_kernel
from ..brand_kernel.schema import BrandKernel
from ..platforms import Platform
from ..shared.llm import LLMPort, resolve_llm
from ..shared_calendar.models import ContentItem, ContentStatus
from ..shared_calendar.repository import CalendarRepository


@dataclass(frozen=True, slots=True)
class TrendItem:
    """Un signal de veille brut, avant tout choix éditorial."""

    title: str
    url: str
    source: str
    summary: str = ""
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class Topic:
    """Le sujet retenu par `choose_topic()`, prêt pour `write()`."""

    title: str
    angle: str
    source_url: str = ""


@dataclass(frozen=True, slots=True)
class Draft:
    """Le brouillon produit par `write()`.

    `body` porte le contenu principal — script complet pour une vidéo/short,
    texte du post pour une plateforme textuelle, légende pour un carousel.
    `image_prompt` est un prompt de génération d'image RÉUTILISABLE (même
    thème visuel à chaque appel, dérivé du Brand Kernel) plutôt qu'une image
    déjà produite. `carousel_pages` ne sert qu'aux formats carousel (Instagram) :
    le contenu de chaque page, l'auteur applique son propre template.
    """

    title: str
    body: str
    image_prompt: str | None = None
    carousel_pages: tuple[str, ...] = ()
    topic_summary: str = ""


def _render_body_for_storage(draft: Draft) -> str:
    """Sérialise `Draft` en un seul texte : `content_items.body` est le seul
    champ texte libre du schéma (Lot 2, déjà figé) — `image_prompt` et
    `carousel_pages` doivent donc y être inclus, jamais silencieusement
    perdus entre `write()` et la relecture du brouillon."""
    parts = [draft.body]
    if draft.carousel_pages:
        parts.append("--- PAGES DU CAROUSEL ---")
        parts.extend(f"[Page {i}] {page}" for i, page in enumerate(draft.carousel_pages, start=1))
    if draft.image_prompt:
        parts.append(f"--- PROMPT IMAGE (thème réutilisable) ---\n{draft.image_prompt}")
    return "\n\n".join(parts)


class PlatformPipeline(ABC):
    """Contrat `watch → choose_topic → write → submit` d'un pipeline de plateforme."""

    platform: Platform

    def __init__(
        self,
        *,
        repository: CalendarRepository,
        brand_kernel: BrandKernel | None = None,
        llm: LLMPort | None = None,
        offline: bool = False,
    ) -> None:
        self.repository = repository
        self.brand_kernel = brand_kernel or load_brand_kernel()
        self.llm = llm or resolve_llm(offline=offline, api_key=os.getenv("GROQ_API_KEY", "").strip())
        self.offline = offline
        self.logger = logging.getLogger(f"pilotage.pipelines.{self.platform.value}")

    # ------------------------------------------------------------------ #
    # Étapes propres à chaque plateforme
    # ------------------------------------------------------------------ #
    @abstractmethod
    def watch(self) -> list[TrendItem]:
        """Veille propre à la plateforme. Jamais critique : voir `run()`."""

    @abstractmethod
    def choose_topic(self, trends: list[TrendItem]) -> Topic:
        """Choisit un sujet. Doit fonctionner même si `trends` est vide."""

    @abstractmethod
    def write(self, topic: Topic) -> Draft:
        """Génère le brouillon. Charge et applique le Brand Kernel ici,
        jamais ailleurs — c'est ce qui garantit que changer le ton à un seul
        endroit change les six plateformes."""

    # ------------------------------------------------------------------ #
    # Étape commune
    # ------------------------------------------------------------------ #
    def submit(self, draft: Draft) -> int:
        """Enregistre le brouillon en base (`status = 'drafted'`) et tente,
        sans jamais échouer pour autant, une mention croisée facultative vers
        un contenu déjà publié sur une autre plateforme."""
        item_id = self.repository.add_item(
            ContentItem(
                platform=self.platform,
                title=draft.title,
                topic=draft.topic_summary or None,
                body=_render_body_for_storage(draft),
                status=ContentStatus.DRAFTED,
            )
        )
        try:
            candidate = self.repository.suggest_cross_reference(item_id)
        except Exception:  # noqa: BLE001 - facultatif, ne doit jamais interrompre submit()
            self.logger.debug("Mention croisée indisponible pour l'item %s", item_id, exc_info=True)
        else:
            if candidate is not None:
                self.logger.info("Mention croisée suggérée : %s → %s", item_id, candidate.title)
        return item_id

    # ------------------------------------------------------------------ #
    # Orchestration
    # ------------------------------------------------------------------ #
    def run(self) -> int:
        """Enchaîne `watch → choose_topic → write → submit`. Renvoie l'id du
        `content_item` créé. Seule `watch()` peut échouer sans faire échouer
        le run : une exception y est journalisée puis avalée."""
        started = time.monotonic()
        self.logger.info("▶ run %s", self.platform.value)

        trends = self._safe_watch()
        topic = self.choose_topic(trends)
        draft = self.write(topic)
        item_id = self.submit(draft)

        duration = time.monotonic() - started
        self.logger.info(
            "✔ run %s (%.1fs) — brouillon #%s : %s", self.platform.value, duration, item_id, draft.title
        )
        return item_id

    def _safe_watch(self) -> list[TrendItem]:
        try:
            return self.watch()
        except Exception as exc:  # noqa: BLE001 - veille non critique par construction
            self.logger.warning("Veille %s indisponible : %s", self.platform.value, exc, exc_info=True)
            return []
