"""Tests du contrat commun `PlatformPipeline` (lot 3, issue #56).

Utilise une sous-classe factice minimale plutôt que `YouTubePipeline` : ce
fichier ne teste QUE le comportement partagé (orchestration, non-criticité
de `watch()`, persistance de `submit()`), jamais la logique propre à une
plateforme.
"""

from __future__ import annotations

from pilotage.brand_kernel.schema import BrandKernel
from pilotage.pipelines.base import Draft, PlatformPipeline, Topic, TrendItem
from pilotage.platforms import Platform
from pilotage.shared.llm import FakeLLM
from pilotage.shared_calendar.models import ContentItem, ContentStatus
from pilotage.shared_calendar.repository import CalendarRepository


class _DummyPipeline(PlatformPipeline):
    platform = Platform.X

    def __init__(self, *, watch_raises: bool = False, trends: list[TrendItem] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._watch_raises = watch_raises
        self._trends = trends or []

    def watch(self) -> list[TrendItem]:
        if self._watch_raises:
            raise RuntimeError("veille cassée")
        return self._trends

    def choose_topic(self, trends: list[TrendItem]) -> Topic:
        return Topic(title="Sujet de test", angle="Angle de test")

    def write(self, topic: Topic) -> Draft:
        return Draft(title=topic.title, body="Corps du brouillon de test.")


def _pipeline(repository: CalendarRepository, brand_kernel: BrandKernel, **kwargs) -> _DummyPipeline:
    return _DummyPipeline(
        repository=repository, brand_kernel=brand_kernel, llm=FakeLLM(), offline=True, **kwargs
    )


def test_run_enchaine_les_quatre_etapes_et_enregistre_un_brouillon(calendar_repository, brand_kernel):
    pipeline = _pipeline(calendar_repository, brand_kernel)

    item_id = pipeline.run()

    items = calendar_repository.list_by_platform(Platform.X)
    assert len(items) == 1
    assert items[0].id == item_id
    assert items[0].title == "Sujet de test"
    assert items[0].status is ContentStatus.DRAFTED


def test_une_veille_en_panne_ne_fait_pas_echouer_le_run(calendar_repository, brand_kernel):
    pipeline = _pipeline(calendar_repository, brand_kernel, watch_raises=True)

    item_id = pipeline.run()  # ne doit pas lever

    assert item_id is not None
    assert len(calendar_repository.list_by_platform(Platform.X)) == 1


def test_watch_est_la_seule_etape_non_critique(calendar_repository, brand_kernel):
    """Contrairement à `watch()`, une exception dans `write()` doit se propager."""

    class _EchecEcriture(_DummyPipeline):
        def write(self, topic: Topic) -> Draft:
            raise RuntimeError("écriture cassée")

    pipeline = _EchecEcriture(
        repository=calendar_repository, brand_kernel=brand_kernel, llm=FakeLLM(), offline=True
    )

    try:
        pipeline.run()
    except RuntimeError as exc:
        assert "écriture cassée" in str(exc)
    else:
        raise AssertionError("write() aurait dû laisser l'exception se propager")


def test_submit_tente_une_mention_croisee_sans_jamais_echouer(calendar_repository, brand_kernel):
    # Un contenu déjà publié sur une autre plateforme, candidat à la suggestion.
    blog_id = calendar_repository.add_item(ContentItem(platform=Platform.BLOG, title="Article publié"))
    calendar_repository.update_status(blog_id, ContentStatus.PUBLISHED)

    pipeline = _pipeline(calendar_repository, brand_kernel)
    item_id = pipeline.run()

    item = calendar_repository.list_by_platform(Platform.X)[0]
    assert item.id == item_id
    assert item.cross_ref_id == blog_id
