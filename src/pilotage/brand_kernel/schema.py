"""Structure typée du Brand Kernel (dataclasses miroir de `brand_kernel.yaml`).

Convention reprise de `blogseo.infrastructure.config.settings` : dataclasses
gelées (`frozen=True, slots=True`), aucune valeur d'identité en dur ici — tout
vient du YAML, assemblé par `loader.load_brand_kernel()`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pilotage.platforms import Platform


@dataclass(frozen=True, slots=True)
class Handles:
    """Comptes officiels, pour les mentions croisées et les cartes de fin.

    `None` signifie « pas encore de compte » (légitime : certains comptes
    restent à créer, voir CADRAGE.md décision 4) — à distinguer d'un `TODO`,
    qui signifie « décision pas encore prise » et fait échouer le chargement.
    """

    youtube: str | None
    linkedin: str | None
    github: str | None
    blog: str | None
    tiktok: str | None
    instagram: str | None
    x: str | None
    facebook: str | None
    telegram_channel: str | None


@dataclass(frozen=True, slots=True)
class Identity:
    name: str
    slogan: str
    baseline: str
    language: str
    handles: Handles


@dataclass(frozen=True, slots=True)
class Voice:
    tone: tuple[str, ...]
    address: str
    forbidden: tuple[str, ...]
    signature_phrases: tuple[str, ...]
    emoji_policy: str


@dataclass(frozen=True, slots=True)
class Colors:
    primary: str
    secondary: str
    accent: str
    background: str
    text: str


@dataclass(frozen=True, slots=True)
class Logo:
    path: str
    safe_zone_ratio: float


@dataclass(frozen=True, slots=True)
class Fonts:
    heading: str
    body: str


@dataclass(frozen=True, slots=True)
class Visual:
    colors: Colors
    logo: Logo
    fonts: Fonts
    thumbnail_style: str


@dataclass(frozen=True, slots=True)
class Audience:
    country: str
    segments: tuple[str, ...]
    # Niveau technique par plateforme : l'audience réelle diffère d'un réseau
    # à l'autre. Une clé par plateforme pilotée (voir `Platform.piloted()`).
    technical_level_by_platform: dict[Platform, str]
    pain_points: tuple[str, ...]
    currency: str


@dataclass(frozen=True, slots=True)
class Offer:
    id: str
    # `name`/`url`/`call_to_action` sont `None` pour un emplacement d'offre pas
    # encore pourvu (ex. produit propre pas encore décidé) — toujours `active
    # = False` dans ce cas, `active_offers` les filtre.
    name: str | None
    url: str | None
    active: bool
    commission: str | None
    call_to_action: str | None


@dataclass(frozen=True, slots=True)
class Tracking:
    """Paramètre de suivi ajouté aux liens sortants (CADRAGE.md décision 6)."""

    param: str
    scheme: str

    def value_for(self, platform: Platform) -> str:
        return self.scheme.format(platform=platform.value)

    def query_string(self, platform: Platform) -> str:
        return f"{self.param}={self.value_for(platform)}"

    def apply(self, url: str, platform: Platform) -> str:
        """Ajoute le paramètre de suivi à `url` pour `platform`."""
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{self.query_string(platform)}"


@dataclass(frozen=True, slots=True)
class BrandKernel:
    """Agrégat : l'identité de marque complète, chargée une fois par process."""

    version: int
    identity: Identity
    voice: Voice
    visual: Visual
    audience: Audience
    offers: tuple[Offer, ...]
    tracking: Tracking

    @property
    def active_offers(self) -> tuple[Offer, ...]:
        """Seules ces offres peuvent être citées par un rédacteur."""
        return tuple(offer for offer in self.offers if offer.active)
