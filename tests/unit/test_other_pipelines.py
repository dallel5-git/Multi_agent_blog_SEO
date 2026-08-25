"""Tests des 5 pipelines dupliqués depuis le pilote YouTube (issues #58-#62).

Un bloc paramétré vérifie le comportement COMMUN aux cinq (offre par
`PlatformPipeline`, déjà testé en détail dans `test_pipelines_base.py`) ;
le reste vérifie ce qui est propre à chaque format de contenu.
"""

from __future__ import annotations

import pytest

from pilotage.pipelines.base import Topic
from pilotage.pipelines.facebook import FacebookPipeline
from pilotage.pipelines.facebook.writer import generate_post as facebook_generate_post
from pilotage.pipelines.instagram import InstagramPipeline
from pilotage.pipelines.instagram.writer import generate_carousel
from pilotage.pipelines.telegram_channel import TelegramChannelPipeline
from pilotage.pipelines.telegram_channel.writer import generate_message
from pilotage.pipelines.tiktok import TikTokPipeline
from pilotage.pipelines.tiktok.writer import generate_script as tiktok_generate_script
from pilotage.pipelines.x import XPipeline
from pilotage.pipelines.x.writer import generate_post as x_generate_post
from pilotage.platforms import Platform
from pilotage.shared.llm import FakeLLM
from pilotage.shared_calendar.models import ContentStatus

_PIPELINE_CLASSES = {
    Platform.TIKTOK: TikTokPipeline,
    Platform.INSTAGRAM: InstagramPipeline,
    Platform.X: XPipeline,
    Platform.FACEBOOK: FacebookPipeline,
    Platform.TELEGRAM_CHANNEL: TelegramChannelPipeline,
}


# --------------------------------------------------------------------------- #
# Comportement commun aux cinq pipelines
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("platform", list(_PIPELINE_CLASSES), ids=lambda p: p.value)
def test_chaque_pipeline_tourne_hors_ligne_et_najoute_quun_seul_brouillon(
    platform, calendar_repository, brand_kernel
):
    pipeline_cls = _PIPELINE_CLASSES[platform]
    pipeline = pipeline_cls(
        repository=calendar_repository, brand_kernel=brand_kernel, llm=FakeLLM(), offline=True
    )

    item_id = pipeline.run()

    items = calendar_repository.list_by_platform(platform)
    assert len(items) == 1
    assert items[0].id == item_id
    assert items[0].status is ContentStatus.DRAFTED

    for autre in Platform:
        if autre is platform:
            continue
        assert calendar_repository.list_by_platform(autre) == []


@pytest.mark.parametrize("platform", list(_PIPELINE_CLASSES), ids=lambda p: p.value)
def test_chaque_pipeline_survit_a_une_veille_en_panne(platform, calendar_repository, brand_kernel):
    pipeline_cls = _PIPELINE_CLASSES[platform]

    class _VeilleCassee(pipeline_cls):
        def watch(self):
            raise RuntimeError("veille cassée")

    pipeline = _VeilleCassee(
        repository=calendar_repository, brand_kernel=brand_kernel, llm=FakeLLM(), offline=True
    )

    item_id = pipeline.run()  # ne doit pas lever

    assert item_id is not None


# --------------------------------------------------------------------------- #
# Instagram — carousel : le format même de la décision de l'auteur
# --------------------------------------------------------------------------- #
def test_instagram_produit_des_pages_de_carousel_et_un_prompt_de_theme(brand_kernel):
    topic = Topic(title="5 automatisations n8n", angle="Angle pratique.")

    draft = generate_carousel(topic, brand_kernel, FakeLLM())

    assert draft.carousel_pages  # jamais vide, même en repli
    assert draft.image_prompt is not None
    assert brand_kernel.visual.thumbnail_style in draft.image_prompt


def test_instagram_conserve_les_pages_du_carousel_apres_persistance(
    calendar_repository, brand_kernel
):
    pipeline = InstagramPipeline(
        repository=calendar_repository, brand_kernel=brand_kernel, llm=FakeLLM(), offline=True
    )

    pipeline.run()

    item = calendar_repository.list_by_platform(Platform.INSTAGRAM)[0]
    assert "PAGES DU CAROUSEL" in item.body
    assert "PROMPT IMAGE" in item.body


# --------------------------------------------------------------------------- #
# TikTok — script court + prompt de couverture, bloc de marque COURT
# --------------------------------------------------------------------------- #
def test_tiktok_produit_un_script_et_un_prompt_de_couverture_verticale(brand_kernel):
    topic = Topic(title="3 automatisations n8n en 60 secondes", angle="Angle rapide.")

    draft = tiktok_generate_script(topic, brand_kernel, FakeLLM())

    assert draft.body
    assert draft.image_prompt is not None
    assert "9:16" in draft.image_prompt


def test_tiktok_utilise_le_bloc_de_marque_court(brand_kernel):
    llm = FakeLLM()
    topic = Topic(title="T", angle="A")

    tiktok_generate_script(topic, brand_kernel, llm)

    system_prompt_recu = llm.calls[0][0]
    assert "(court)" in system_prompt_recu  # signature du bloc court, voir render_prompt_block


# --------------------------------------------------------------------------- #
# X — post ou thread, bloc de marque COURT, jamais d'image_prompt
# --------------------------------------------------------------------------- #
def test_x_utilise_le_bloc_de_marque_court_et_ne_genere_pas_dimage(brand_kernel):
    llm = FakeLLM()
    topic = Topic(title="T", angle="A")

    draft = x_generate_post(topic, brand_kernel, llm)

    assert "(court)" in llm.calls[0][0]
    assert draft.image_prompt is None


# --------------------------------------------------------------------------- #
# Facebook — post + visuel, bloc de marque COMPLET
# --------------------------------------------------------------------------- #
def test_facebook_produit_un_post_et_un_prompt_de_visuel(brand_kernel):
    llm = FakeLLM()
    topic = Topic(title="Automatiser sa prospection", angle="Angle PME.")

    draft = facebook_generate_post(topic, brand_kernel, llm)

    assert draft.body
    assert draft.image_prompt is not None
    assert "(court)" not in llm.calls[0][0]  # Facebook n'est pas un format bref


# --------------------------------------------------------------------------- #
# Telegram (canal) — message texte simple, jamais d'image_prompt
# --------------------------------------------------------------------------- #
def test_telegram_channel_produit_un_message_sans_image_prompt(brand_kernel):
    topic = Topic(title="Nouvel article du blog", angle="Message court.")

    draft = generate_message(topic, brand_kernel, FakeLLM())

    assert draft.body
    assert draft.image_prompt is None
    assert draft.carousel_pages == ()
