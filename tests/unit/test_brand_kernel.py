"""Tests du Brand Kernel (lot 1) : chargement, validation stricte, cache,
`render_prompt_block()`.

Ces tests n'utilisent jamais le `brand_kernel.yaml` réel du projet — il porte
encore des `TODO` tant que l'auteur n'a pas tranché toutes les décisions de
CADRAGE.md §5, et il finira par en être dépourvu. Chaque test construit son
propre YAML minimal dans `tmp_path`, pour rester indépendant du contenu réel.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from pilotage.brand_kernel.loader import load_brand_kernel, render_prompt_block
from pilotage.brand_kernel.schema import BrandKernel, Tracking
from pilotage.platforms import Platform


def _kernel_data() -> dict[str, Any]:
    """Un Brand Kernel complet et valide, sans aucun `TODO`."""
    return {
        "version": 1,
        "identity": {
            "name": "Oussama Dallel",
            "slogan": "Prenez le contrôle de votre temps grâce à l'IA",
            "baseline": "Un ingénieur tunisien qui automatise avec l'IA, sans jargon inutile.",
            "language": "fr",
            "handles": {
                "youtube": "https://www.youtube.com/@oussamadallel5",
                "linkedin": "https://www.linkedin.com/in/oussama-dallel-120143209/",
                "github": "https://github.com/dallel5-git",
                "blog": "https://oussama-ai-blog-v1.vercel.app",
                "tiktok": None,
                "instagram": None,
                "x": None,
                "facebook": None,
                "telegram_channel": None,
            },
        },
        "voice": {
            "tone": ["direct", "concret", "pédagogue"],
            "address": "tu",
            "forbidden": ["promesses de revenus chiffrées"],
            "signature_phrases": ["Prends le contrôle de ton temps."],
            "emoji_policy": "parcimonieux",
        },
        "visual": {
            "colors": {
                "primary": "#1D4ED8",
                "secondary": "#0F172A",
                "accent": "#F59E0B",
                "background": "#FFFFFF",
                "text": "#111827",
            },
            "logo": {"path": "assets/brand/logo.svg", "safe_zone_ratio": 0.1},
            "fonts": {"heading": "Inter", "body": "Inter"},
            "thumbnail_style": "Fond sombre, texte blanc, un mot-clé en accent.",
        },
        "audience": {
            "country": "Tunisie",
            "segments": ["étudiants", "PME et petits business"],
            "technical_level_by_platform": {
                "youtube": "mixte",
                "tiktok": "débutant",
                "instagram": "débutant",
                "x": "intermédiaire",
                "facebook": "débutant",
                "telegram_channel": "intermédiaire",
            },
            "pain_points": ["manque de temps", "peur de la technique"],
            "currency": "TND",
        },
        "offers": [
            {
                "id": "n8n",
                "name": "n8n",
                "url": "https://n8n.partner/aff",
                "active": True,
                "commission": "20%",
                "call_to_action": "Automatise avec n8n",
            },
            {
                "id": "make",
                "name": "Make",
                "url": "https://make.partner/aff",
                "active": False,
                "commission": "15%",
                "call_to_action": "Essaie Make",
            },
        ],
        "tracking": {"param": "ref", "scheme": "od-{platform}"},
    }


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    fichier = path / "brand_kernel.yaml"
    fichier.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return fichier


def _set_path(data: dict, dotted_path: str, value: Any) -> None:
    """Mutation en place d'une valeur imbriquée, ex. `voice.tone`."""
    *tete, feuille = dotted_path.split(".")
    cible = data
    for cle in tete:
        cible = cible[cle]
    cible[feuille] = value


# --------------------------------------------------------------------------- #
# Chargement réussi
# --------------------------------------------------------------------------- #
def test_load_brand_kernel_construit_un_brand_kernel_complet(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())

    kernel = load_brand_kernel(path=fichier)

    assert isinstance(kernel, BrandKernel)
    assert kernel.identity.name == "Oussama Dallel"
    assert kernel.voice.address == "tu"
    assert kernel.audience.technical_level_by_platform[Platform.TIKTOK] == "débutant"
    assert kernel.tracking == Tracking(param="ref", scheme="od-{platform}")


def test_load_brand_kernel_met_en_cache_par_chemin(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())

    premier = load_brand_kernel(path=fichier)
    second = load_brand_kernel(path=fichier)

    assert premier is second


def test_load_brand_kernel_lit_le_chemin_depuis_lenvironnement(tmp_path, monkeypatch):
    fichier = _write_yaml(tmp_path, _kernel_data())
    monkeypatch.setenv("BRAND_KERNEL_PATH", str(fichier))

    kernel = load_brand_kernel()

    assert kernel.identity.name == "Oussama Dallel"


def test_active_offers_ne_garde_que_les_offres_actives(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())

    kernel = load_brand_kernel(path=fichier)

    assert [o.id for o in kernel.active_offers] == ["n8n"]


# --------------------------------------------------------------------------- #
# Échecs de validation
# --------------------------------------------------------------------------- #
def test_load_brand_kernel_echoue_explicitement_sil_reste_un_todo(tmp_path):
    data = _kernel_data()
    _set_path(data, "voice.tone", "TODO")
    fichier = _write_yaml(tmp_path, data)

    with pytest.raises(ValueError, match="TODO"):
        load_brand_kernel(path=fichier)


def test_load_brand_kernel_echoue_si_une_section_obligatoire_manque(tmp_path):
    data = _kernel_data()
    del data["tracking"]
    fichier = _write_yaml(tmp_path, data)

    with pytest.raises(ValueError, match="tracking"):
        load_brand_kernel(path=fichier)


def test_load_brand_kernel_echoue_si_une_plateforme_pilotee_manque_au_niveau_technique(tmp_path):
    data = _kernel_data()
    del data["audience"]["technical_level_by_platform"]["tiktok"]
    fichier = _write_yaml(tmp_path, data)

    with pytest.raises(ValueError, match="tiktok"):
        load_brand_kernel(path=fichier)


def test_load_brand_kernel_echoue_sur_une_plateforme_inconnue(tmp_path):
    data = _kernel_data()
    data["audience"]["technical_level_by_platform"]["mastodon"] = "mixte"
    fichier = _write_yaml(tmp_path, data)

    with pytest.raises(ValueError):
        load_brand_kernel(path=fichier)


def test_load_brand_kernel_echoue_si_le_fichier_nexiste_pas(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_brand_kernel(path=tmp_path / "absent.yaml")


def test_load_brand_kernel_echoue_si_une_offre_active_na_pas_de_lien(tmp_path):
    """Une offre active sans lien serait un contenu publié cassé sur les six
    plateformes — refusé au même titre qu'un `TODO` oublié."""
    data = _kernel_data()
    data["offers"][0]["active"] = True
    data["offers"][0]["url"] = None
    fichier = _write_yaml(tmp_path, data)

    with pytest.raises(ValueError, match="n8n"):
        load_brand_kernel(path=fichier)


# --------------------------------------------------------------------------- #
# Tracking (CADRAGE.md décision 6)
# --------------------------------------------------------------------------- #
def test_tracking_apply_ajoute_le_parametre_a_une_url_sans_requete():
    tracking = Tracking(param="ref", scheme="od-{platform}")

    assert tracking.apply("https://n8n.io", Platform.YOUTUBE) == "https://n8n.io?ref=od-youtube"


def test_tracking_apply_ajoute_le_parametre_a_une_url_avec_requete_existante():
    tracking = Tracking(param="ref", scheme="od-{platform}")

    resultat = tracking.apply("https://n8n.io?utm=x", Platform.TIKTOK)

    assert resultat == "https://n8n.io?utm=x&ref=od-tiktok"


# --------------------------------------------------------------------------- #
# render_prompt_block()
# --------------------------------------------------------------------------- #
def test_render_prompt_block_reflete_le_ton_et_la_plateforme(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())
    kernel = load_brand_kernel(path=fichier)

    bloc = render_prompt_block(kernel, Platform.YOUTUBE)

    assert "YouTube" in bloc
    assert "direct" in bloc
    assert "mixte" in bloc  # niveau technique de YouTube


def test_render_prompt_block_change_de_niveau_technique_selon_la_plateforme(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())
    kernel = load_brand_kernel(path=fichier)

    bloc_youtube = render_prompt_block(kernel, Platform.YOUTUBE)
    bloc_tiktok = render_prompt_block(kernel, Platform.TIKTOK)

    assert "mixte" in bloc_youtube
    assert "débutant" in bloc_tiktok


def test_render_prompt_block_ninclut_que_les_offres_actives_avec_lien_trackee(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())
    kernel = load_brand_kernel(path=fichier)

    bloc = render_prompt_block(kernel, Platform.X)

    assert "n8n" in bloc
    assert "ref=od-x" in bloc
    assert "Make" not in bloc


def test_render_prompt_block_ne_change_pas_le_code_si_le_ton_change(tmp_path):
    """Critère d'acceptation de l'issue : changer le ton à un seul endroit
    (le YAML) doit changer le bloc produit pour toutes les plateformes,
    sans toucher au code de `render_prompt_block()`."""
    data = _kernel_data()
    dossier_avant = tmp_path / "avant"
    dossier_avant.mkdir()
    fichier_avant = _write_yaml(dossier_avant, data)

    data_modifiee = copy.deepcopy(data)
    data_modifiee["voice"]["tone"] = ["chaleureux", "inspirant"]
    dossier_apres = tmp_path / "apres"
    dossier_apres.mkdir()
    fichier_apres = _write_yaml(dossier_apres, data_modifiee)

    bloc_avant = render_prompt_block(load_brand_kernel(path=fichier_avant), Platform.FACEBOOK)
    bloc_apres = render_prompt_block(load_brand_kernel(path=fichier_apres), Platform.FACEBOOK)

    assert "direct" in bloc_avant
    assert "chaleureux" in bloc_apres
    assert "chaleureux" not in bloc_avant


# --------------------------------------------------------------------------- #
# render_prompt_block() — variante courte (X, TikTok)
# --------------------------------------------------------------------------- #
def test_render_prompt_block_short_est_nettement_plus_court(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())
    kernel = load_brand_kernel(path=fichier)

    bloc_complet = render_prompt_block(kernel, Platform.X)
    bloc_court = render_prompt_block(kernel, Platform.X, short=True)

    assert len(bloc_court) < len(bloc_complet)


def test_render_prompt_block_short_garde_le_ton_les_interdits_et_le_niveau(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())
    kernel = load_brand_kernel(path=fichier)

    bloc = render_prompt_block(kernel, Platform.TIKTOK, short=True)

    assert "direct" in bloc
    assert "promesses de revenus chiffrées" in bloc
    assert "débutant" in bloc  # niveau technique de TikTok


def test_render_prompt_block_short_omet_la_baseline_et_les_details_visuels(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())
    kernel = load_brand_kernel(path=fichier)

    bloc = render_prompt_block(kernel, Platform.X, short=True)

    assert "Baseline" not in bloc
    assert kernel.identity.baseline not in bloc
    assert kernel.visual.colors.primary not in bloc


def test_render_prompt_block_short_ninclut_que_les_offres_actives(tmp_path):
    fichier = _write_yaml(tmp_path, _kernel_data())
    kernel = load_brand_kernel(path=fichier)

    bloc = render_prompt_block(kernel, Platform.X, short=True)

    assert "n8n" in bloc
    assert "ref=od-x" in bloc
    assert "Make" not in bloc
