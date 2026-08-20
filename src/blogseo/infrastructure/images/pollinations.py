"""Génération d'image de couverture via Pollinations.ai — gratuit, sans clé.

L'API est un simple GET sur une URL contenant le prompt : aucune inscription,
aucun quota déclaré. En cas d'échec, l'adapter génère une image de secours
locale (dégradé + titre) avec Pillow, ou renvoie None si Pillow est absent.
"""

from __future__ import annotations

import hashlib
import logging
import textwrap
import urllib.parse
from pathlib import Path

import requests

from ...domain.ports.publishing import ImageGeneratorPort

logger = logging.getLogger(__name__)

_BASE_URL = "https://image.pollinations.ai/prompt"


class PollinationsImageGenerator(ImageGeneratorPort):
    """Couverture 1280×720 générée à la volée, avec repli local."""

    name = "pollinations"

    def __init__(
        self,
        output_dir: Path,
        *,
        timeout_s: int = 90,
        model: str = "flux",
        session: requests.Session | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.timeout_s = timeout_s
        self.model = model
        self._session = session or requests.Session()

    def generate(self, prompt: str, *, slug: str, width: int = 1280, height: int = 720) -> Path | None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = self.output_dir / f"{slug}.jpg"

        encoded = urllib.parse.quote(prompt[:900], safe="")
        # `seed` déterministe : relancer le même article régénère la même image.
        seed = int(hashlib.blake2b(slug.encode(), digest_size=4).hexdigest(), 16) % 1_000_000
        url = f"{_BASE_URL}/{encoded}"
        params = {
            "width": width, "height": height, "model": self.model,
            "seed": seed, "nologo": "true", "enhance": "true",
        }

        try:
            response = self._session.get(url, params=params, timeout=self.timeout_s)
            if response.status_code >= 400 or not response.content:
                raise requests.RequestException(f"HTTP {response.status_code}")
            content_type = response.headers.get("Content-Type", "")
            if "image" not in content_type:
                raise requests.RequestException(f"Content-Type inattendu : {content_type}")
            target.write_bytes(response.content)
            logger.info("Couverture générée : %s (%s Ko)", target.name, len(response.content) // 1024)
            return target
        except (requests.RequestException, OSError) as exc:
            logger.warning("Pollinations indisponible (%s) — génération de l'image de secours", exc)
            return self._fallback_cover(target, prompt, width, height)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _fallback_cover(target: Path, title: str, width: int, height: int) -> Path | None:
        """Image de secours : dégradé indigo/cyan + titre, aux couleurs du blog."""
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("Pillow absent : aucune image de couverture ne sera associée à l'article")
            return None

        image = Image.new("RGB", (width, height), (11, 13, 20))
        draw = ImageDraw.Draw(image)

        # Dégradé diagonal du bleu indigo vers le cyan (palette du blog).
        for y in range(height):
            ratio = y / height
            draw.line(
                [(0, y), (width, y)],
                fill=(
                    int(17 + 46 * ratio),
                    int(20 + 90 * ratio),
                    int(38 + 120 * ratio),
                ),
            )

        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
        except OSError:
            font = ImageFont.load_default()

        lines = textwrap.wrap(title[:120], width=28)[:4]
        y = height // 2 - (len(lines) * 70) // 2
        for line in lines:
            draw.text((80, y), line, font=font, fill=(235, 240, 255))
            y += 70

        try:
            image.save(target, "JPEG", quality=88)
        except OSError as exc:
            logger.warning("Image de secours non enregistrée : %s", exc)
            return None
        logger.info("Image de secours générée : %s", target.name)
        return target
