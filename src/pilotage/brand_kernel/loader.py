"""Chargement et validation du Brand Kernel.

Contrat :

1. chemin par défaut = `brand_kernel.yaml` à côté de ce module ;
2. surchargeable par la variable d'environnement `BRAND_KERNEL_PATH`, ou par
   l'argument `path` (utile pour les tests) ;
3. lecture avec `yaml.safe_load` ;
4. échec explicite (`ValueError`) si une section obligatoire manque ou si une
   valeur vaut encore la chaîne littérale `"TODO"` — mieux vaut planter au
   démarrage que publier un visuel aux mauvaises couleurs sur six comptes ;
5. résultat mis en cache (`functools.cache`) : le fichier est lu une fois par
   process, pas une fois par agent.

`render_prompt_block()` produit le bloc de texte injecté en tête du prompt
système de chaque rédacteur : il ne lit que le `BrandKernel` déjà validé, donc
aucune valeur d'identité n'est jamais écrite en dur dans le code Python.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from pilotage.platforms import Platform

from .schema import (
    Audience,
    BrandKernel,
    Colors,
    Fonts,
    Handles,
    Identity,
    Logo,
    Offer,
    Tracking,
    Visual,
    Voice,
)

DEFAULT_BRAND_KERNEL_PATH = Path(__file__).resolve().parent / "brand_kernel.yaml"
_ENV_VAR = "BRAND_KERNEL_PATH"
_TODO = "TODO"


def _resolve_path(path: Path | None) -> Path:
    if path is not None:
        return path
    override = os.getenv(_ENV_VAR, "").strip()
    if override:
        return Path(override)
    return DEFAULT_BRAND_KERNEL_PATH


def _find_todos(value: Any, trail: str = "") -> list[str]:
    """Chemins pointés (`voice.tone`, `offers[0].url`...) encore à `TODO`."""
    if isinstance(value, dict):
        trouves: list[str] = []
        for cle, sous_valeur in value.items():
            prefixe = f"{trail}.{cle}" if trail else str(cle)
            trouves.extend(_find_todos(sous_valeur, prefixe))
        return trouves
    if isinstance(value, list):
        trouves = []
        for index, sous_valeur in enumerate(value):
            trouves.extend(_find_todos(sous_valeur, f"{trail}[{index}]"))
        return trouves
    if value == _TODO:
        return [trail]
    return []


def _require(data: dict, cle: str, contexte: str) -> Any:
    if cle not in data:
        raise ValueError(f"Brand Kernel invalide : section « {contexte}.{cle} » manquante")
    return data[cle]


def _build_handles(data: dict) -> Handles:
    return Handles(
        youtube=data.get("youtube"),
        linkedin=data.get("linkedin"),
        github=data.get("github"),
        blog=data.get("blog"),
        tiktok=data.get("tiktok"),
        instagram=data.get("instagram"),
        x=data.get("x"),
        facebook=data.get("facebook"),
        telegram_channel=data.get("telegram_channel"),
    )


def _build_identity(data: dict) -> Identity:
    return Identity(
        name=_require(data, "name", "identity"),
        slogan=_require(data, "slogan", "identity"),
        baseline=_require(data, "baseline", "identity"),
        language=_require(data, "language", "identity"),
        handles=_build_handles(_require(data, "handles", "identity")),
    )


def _build_voice(data: dict) -> Voice:
    return Voice(
        tone=tuple(_require(data, "tone", "voice")),
        address=_require(data, "address", "voice"),
        forbidden=tuple(_require(data, "forbidden", "voice")),
        signature_phrases=tuple(_require(data, "signature_phrases", "voice")),
        emoji_policy=_require(data, "emoji_policy", "voice"),
    )


def _build_visual(data: dict) -> Visual:
    colors_data = _require(data, "colors", "visual")
    colors = Colors(
        primary=_require(colors_data, "primary", "visual.colors"),
        secondary=_require(colors_data, "secondary", "visual.colors"),
        accent=_require(colors_data, "accent", "visual.colors"),
        background=_require(colors_data, "background", "visual.colors"),
        text=_require(colors_data, "text", "visual.colors"),
    )
    logo_data = _require(data, "logo", "visual")
    logo = Logo(
        path=_require(logo_data, "path", "visual.logo"),
        safe_zone_ratio=float(_require(logo_data, "safe_zone_ratio", "visual.logo")),
    )
    fonts_data = _require(data, "fonts", "visual")
    fonts = Fonts(
        heading=_require(fonts_data, "heading", "visual.fonts"),
        body=_require(fonts_data, "body", "visual.fonts"),
    )
    return Visual(
        colors=colors,
        logo=logo,
        fonts=fonts,
        thumbnail_style=_require(data, "thumbnail_style", "visual"),
    )


def _build_audience(data: dict) -> Audience:
    niveaux_bruts = _require(data, "technical_level_by_platform", "audience")
    try:
        niveaux = {Platform(cle): valeur for cle, valeur in niveaux_bruts.items()}
    except ValueError as exc:
        raise ValueError(
            f"Brand Kernel invalide : audience.technical_level_by_platform contient "
            f"une plateforme inconnue ({exc})"
        ) from exc
    manquantes = set(Platform.piloted()) - set(niveaux)
    if manquantes:
        noms = ", ".join(sorted(p.value for p in manquantes))
        raise ValueError(
            "Brand Kernel invalide : audience.technical_level_by_platform ne couvre "
            f"pas toutes les plateformes pilotées (manque : {noms})"
        )
    return Audience(
        country=_require(data, "country", "audience"),
        segments=tuple(_require(data, "segments", "audience")),
        technical_level_by_platform=niveaux,
        pain_points=tuple(_require(data, "pain_points", "audience")),
        currency=_require(data, "currency", "audience"),
    )


def _build_offers(data: list) -> tuple[Offer, ...]:
    offres = tuple(
        Offer(
            id=_require(offre, "id", "offers"),
            name=_require(offre, "name", "offers"),
            url=offre.get("url"),
            active=bool(_require(offre, "active", "offers")),
            commission=offre.get("commission"),
            call_to_action=offre.get("call_to_action"),
        )
        for offre in data
    )
    sans_lien = [offre.id for offre in offres if offre.active and not offre.url]
    if sans_lien:
        raise ValueError(
            f"Brand Kernel invalide : offre(s) active(s) sans lien — {', '.join(sans_lien)}"
        )
    return offres


def _build_tracking(data: dict) -> Tracking:
    return Tracking(
        param=_require(data, "param", "tracking"),
        scheme=_require(data, "scheme", "tracking"),
    )


@cache
def _load_cached(path: Path) -> BrandKernel:
    if not path.is_file():
        raise FileNotFoundError(f"Brand Kernel introuvable : {path}")

    brut = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    todos = _find_todos(brut)
    if todos:
        liste = ", ".join(sorted(todos))
        raise ValueError(
            f"Brand Kernel incomplet ({path}) : valeurs TODO restantes — {liste}. "
            "Voir CADRAGE.md §5 pour les décisions à figer avant de démarrer le lot 1."
        )

    return BrandKernel(
        version=_require(brut, "version", "brand_kernel"),
        identity=_build_identity(_require(brut, "identity", "brand_kernel")),
        voice=_build_voice(_require(brut, "voice", "brand_kernel")),
        visual=_build_visual(_require(brut, "visual", "brand_kernel")),
        audience=_build_audience(_require(brut, "audience", "brand_kernel")),
        offers=_build_offers(_require(brut, "offers", "brand_kernel")),
        tracking=_build_tracking(_require(brut, "tracking", "brand_kernel")),
    )


def load_brand_kernel(path: Path | None = None) -> BrandKernel:
    """Charge le Brand Kernel, le valide, et met le résultat en cache.

    `path` prime sur `BRAND_KERNEL_PATH`, qui prime sur le chemin par défaut
    (`brand_kernel.yaml` à côté de ce module).
    """
    return _load_cached(_resolve_path(path))


def render_prompt_block(kernel: BrandKernel, platform: Platform, *, short: bool = False) -> str:
    """Bloc de texte injecté en tête du prompt système du rédacteur de `platform`.

    Ne lit que `kernel` : changer une valeur du Brand Kernel change ce bloc
    pour les six plateformes, sans toucher au code des rédacteurs.

    `short=True` produit une variante condensée (ton, interdits, niveau
    technique, offres actives — sans baseline ni détails visuels), pour les
    plateformes à format bref (X, TikTok) : c'est au pipeline de la
    plateforme de décider s'il en a besoin, le Brand Kernel ne présume pas
    du format de chaque plateforme (Lot 3, décision 9 de CADRAGE.md).
    """
    if short:
        return _render_short_block(kernel, platform)
    return _render_full_block(kernel, platform)


def _offer_lines(kernel: BrandKernel, platform: Platform) -> list[str]:
    return [
        f"- {offre.name} → {offre.call_to_action} "
        f"({kernel.tracking.apply(offre.url, platform) if offre.url else '(lien absent)'})"
        for offre in kernel.active_offers
    ]


def _render_short_block(kernel: BrandKernel, platform: Platform) -> str:
    voice = kernel.voice
    niveau_technique = kernel.audience.technical_level_by_platform[platform]

    lignes = [
        f"=== BRAND KERNEL (court) — {kernel.identity.name} ({platform.label}) ===",
        f"Ton : {', '.join(voice.tone)} · adresse {voice.address} · emoji {voice.emoji_policy}",
        f"Interdits : {', '.join(voice.forbidden)}",
        f"Niveau technique visé : {niveau_technique}",
    ]

    lignes_offres = _offer_lines(kernel, platform)
    lignes.append("Offres actives : " + ("; ".join(lignes_offres) if lignes_offres else "aucune"))

    return "\n".join(lignes)


def _render_full_block(kernel: BrandKernel, platform: Platform) -> str:
    identity = kernel.identity
    voice = kernel.voice
    visual = kernel.visual
    audience = kernel.audience
    niveau_technique = audience.technical_level_by_platform[platform]

    lignes = [
        f"=== BRAND KERNEL — {identity.name} ({platform.label}) ===",
        f"Slogan : {identity.slogan}",
        f"Baseline : {identity.baseline}",
        f"Langue : {identity.language}",
        "",
        f"Ton de voix : {', '.join(voice.tone)}",
        f"Adresse au lecteur : {voice.address}",
        f"Politique emoji : {voice.emoji_policy}",
        f"Formules signature : {', '.join(voice.signature_phrases)}",
        f"Interdits : {', '.join(voice.forbidden)}",
        "",
        f"Audience : {', '.join(audience.segments)} ({audience.country})",
        f"Niveau technique visé sur {platform.label} : {niveau_technique}",
        f"Problèmes concrets à adresser : {', '.join(audience.pain_points)}",
        "",
        "Identité visuelle : couleurs "
        f"{visual.colors.primary}/{visual.colors.secondary}/{visual.colors.accent} "
        f"sur fond {visual.colors.background}, texte {visual.colors.text}.",
        f"Style des visuels : {visual.thumbnail_style}",
    ]

    lignes_offres = _offer_lines(kernel, platform)
    if lignes_offres:
        lignes.append("")
        lignes.append("Offres à mentionner si pertinent :")
        lignes.extend(lignes_offres)

    return "\n".join(lignes)
