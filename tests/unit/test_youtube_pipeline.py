"""Tests du pipeline pilote YouTube (lot 3, issue #57)."""

from __future__ import annotations

from pilotage.pipelines.base import Topic, TrendItem
from pilotage.pipelines.youtube import YouTubePipeline
from pilotage.pipelines.youtube.watcher import collect_trends
from pilotage.pipelines.youtube.writer import generate_script
from pilotage.platforms import Platform
from pilotage.shared.llm import FakeLLM
from pilotage.shared_calendar.models import ContentStatus


# --------------------------------------------------------------------------- #
# watcher.collect_trends
# --------------------------------------------------------------------------- #
def test_collect_trends_hors_ligne_ne_fait_aucun_appel_reseau():
    assert collect_trends(offline=True) == []


# --------------------------------------------------------------------------- #
# writer.generate_script
# --------------------------------------------------------------------------- #
def test_generate_script_produit_un_script_et_un_prompt_dimage(brand_kernel):
    topic = Topic(title="5 automatisations n8n", angle="Angle pratique.", source_url="https://exemple.test")
    llm = FakeLLM()

    draft = generate_script(topic, brand_kernel, llm)

    assert draft.title == "5 automatisations n8n"
    assert draft.body  # le LLM factice renvoie un texte non vide
    assert draft.image_prompt is not None
    assert brand_kernel.visual.thumbnail_style in draft.image_prompt
    assert topic.title in draft.image_prompt


def test_generate_script_injecte_le_brand_kernel_dans_le_prompt_systeme(brand_kernel):
    """Le ton de voix doit être injecté, sinon rien ne garantit que le
    brouillon respecte la marque (critère d'acceptation de l'issue #57)."""
    topic = Topic(title="T", angle="A")
    llm = FakeLLM()

    generate_script(topic, brand_kernel, llm)

    system_prompt_recu = llm.calls[0][0]
    assert brand_kernel.identity.name in system_prompt_recu


# --------------------------------------------------------------------------- #
# YouTubePipeline — bout en bout, hors ligne
# --------------------------------------------------------------------------- #
def test_youtube_pipeline_tourne_hors_ligne_sans_reseau_ni_cle(calendar_repository, brand_kernel):
    pipeline = YouTubePipeline(
        repository=calendar_repository, brand_kernel=brand_kernel, llm=FakeLLM(), offline=True
    )

    item_id = pipeline.run()

    items = calendar_repository.list_by_platform(Platform.YOUTUBE)
    assert len(items) == 1
    assert items[0].id == item_id
    assert items[0].status is ContentStatus.DRAFTED
    # Sujet de repli déterministe puisqu'aucune veille n'a tourné hors ligne.
    assert items[0].title == "5 automatisations n8n à connaître en 2026"


def test_youtube_pipeline_ne_touche_aucune_autre_plateforme(calendar_repository, brand_kernel):
    pipeline = YouTubePipeline(
        repository=calendar_repository, brand_kernel=brand_kernel, llm=FakeLLM(), offline=True
    )

    pipeline.run()

    for platform in Platform:
        if platform is Platform.YOUTUBE:
            continue
        assert calendar_repository.list_by_platform(platform) == []


def test_choose_topic_utilise_le_signal_le_plus_score_quand_il_y_en_a(calendar_repository, brand_kernel):
    pipeline = YouTubePipeline(
        repository=calendar_repository, brand_kernel=brand_kernel, llm=FakeLLM(), offline=True
    )
    trends = [
        TrendItem(title="Signal faible", url="https://a.test", source="HN", score=1.0),
        TrendItem(title="Signal fort", url="https://b.test", source="HN", score=99.0),
    ]

    topic = pipeline.choose_topic(trends)

    # Le LLM factice ignore le contenu du prompt : on vérifie seulement que
    # `choose_topic` ne lève pas et retombe proprement sur un JSON exploitable.
    assert topic.title
    assert topic.source_url == "https://b.test"
