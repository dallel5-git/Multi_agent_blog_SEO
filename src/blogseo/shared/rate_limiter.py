"""Rate limiter à fenêtre glissante, indispensable pour rester dans les quotas gratuits.

Gemini free tier plafonne à ~15 requêtes/minute et ~1500/jour selon le modèle ;
Groq applique ses propres limites. Ce limiteur bloque *avant* l'appel plutôt que
de laisser l'API renvoyer un 429, ce qui évite de brûler le quota journalier en
erreurs.

Thread-safe et persistable sur disque pour survivre à un redémarrage du process
(le quota journalier, lui, ne se réinitialise pas au redémarrage).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    """Limites d'un fournisseur."""

    requests_per_minute: int = 15
    requests_per_day: int = 1_500
    min_interval_s: float = 0.0  # espacement minimal forcé entre deux appels


class RateLimiter:
    """Limiteur à double fenêtre (minute + jour)."""

    def __init__(
        self,
        name: str,
        config: RateLimitConfig | None = None,
        *,
        state_file: Path | None = None,
        sleep_fn=time.sleep,
        time_fn=time.monotonic,
        wall_clock_fn=time.time,
    ) -> None:
        self.name = name
        self.config = config or RateLimitConfig()
        self._state_file = state_file
        self._sleep = sleep_fn
        self._now = time_fn
        self._wall = wall_clock_fn
        self._lock = threading.Lock()
        self._minute_window: deque[float] = deque()
        self._day_window: deque[float] = deque()  # horodatages absolus (time.time)
        self._last_call: float | None = None
        self._load_state()

    # ------------------------------------------------------------------ #
    def acquire(self, *, block: bool = True) -> bool:
        """Réserve un jeton. Bloque jusqu'à disponibilité si `block=True`.

        Renvoie False si le quota journalier est épuisé (aucune attente ne peut
        sauver l'appel : l'orchestrateur doit basculer sur le fournisseur de secours).
        """
        with self._lock:
            while True:
                self._evict()

                if len(self._day_window) >= self.config.requests_per_day:
                    logger.warning(
                        "[%s] quota journalier atteint (%s/%s) — bascule sur le fallback",
                        self.name, len(self._day_window), self.config.requests_per_day,
                    )
                    return False

                wait = self._wait_needed()
                if wait <= 0:
                    now = self._now()
                    self._minute_window.append(now)
                    self._day_window.append(self._wall())
                    self._last_call = now
                    self._save_state()
                    return True

                if not block:
                    return False
                logger.info("[%s] rate limit : attente de %.1fs avant le prochain appel", self.name, wait)
                self._sleep(wait)

    def _wait_needed(self) -> float:
        """Secondes à attendre avant qu'un jeton soit disponible."""
        waits = [0.0]
        if len(self._minute_window) >= self.config.requests_per_minute:
            waits.append(60.0 - (self._now() - self._minute_window[0]) + 0.05)
        if self.config.min_interval_s and self._last_call is not None:
            waits.append(self.config.min_interval_s - (self._now() - self._last_call))
        return max(waits)

    def _evict(self) -> None:
        """Purge les horodatages sortis des fenêtres."""
        now = self._now()
        while self._minute_window and now - self._minute_window[0] >= 60.0:
            self._minute_window.popleft()
        day_ago = self._wall() - 86_400
        while self._day_window and self._day_window[0] < day_ago:
            self._day_window.popleft()

    # ------------------------------------------------------------------ #
    @property
    def remaining_today(self) -> int:
        with self._lock:
            self._evict()
            return max(0, self.config.requests_per_day - len(self._day_window))

    def _load_state(self) -> None:
        if not self._state_file or not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            day_ago = self._wall() - 86_400
            self._day_window = deque(t for t in data.get("day", []) if t > day_ago)
        except (OSError, ValueError, TypeError) as exc:  # pragma: no cover - défensif
            logger.debug("[%s] état du rate limiter illisible : %s", self.name, exc)

    def _save_state(self) -> None:
        if not self._state_file:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps({"day": list(self._day_window)}), encoding="utf-8"
            )
        except OSError as exc:  # pragma: no cover - défensif
            logger.debug("[%s] impossible d'écrire l'état du rate limiter : %s", self.name, exc)
