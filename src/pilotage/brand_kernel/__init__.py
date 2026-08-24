"""Brand Kernel — la seule chose obligatoirement partagée par les 6 pipelines.

Un fichier YAML unique (`brand_kernel.yaml`) décrit l'identité de marque :
couleurs, logo, police, ton de voix, slogan, cible, offres d'affiliation.
TOUT agent de rédaction le charge avant de générer quoi que ce soit, quelle
que soit la plateforme :

    from pilotage.brand_kernel import load_brand_kernel, render_prompt_block

    kernel = load_brand_kernel()
    prompt = render_prompt_block(kernel, Platform.YOUTUBE)
"""

from __future__ import annotations

from .loader import DEFAULT_BRAND_KERNEL_PATH, load_brand_kernel, render_prompt_block
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

__all__ = [
    "DEFAULT_BRAND_KERNEL_PATH",
    "load_brand_kernel",
    "render_prompt_block",
    "Audience",
    "BrandKernel",
    "Colors",
    "Fonts",
    "Handles",
    "Identity",
    "Logo",
    "Offer",
    "Tracking",
    "Visual",
    "Voice",
]
