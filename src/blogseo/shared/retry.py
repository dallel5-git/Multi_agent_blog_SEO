"""Décorateur de retry avec backoff exponentiel et jitter.

Utilisé pour tous les appels réseau (LLM, recherche, Telegram, images) afin
d'absorber les coupures passagères sans faire tomber le pipeline entier.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry(
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    give_up_on: tuple[type[BaseException], ...] = (),
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retente `attempts` fois avec un backoff exponentiel + jitter.

    `give_up_on` liste les exceptions pour lesquelles réessayer est inutile
    (ex. quota journalier épuisé) : elles sont relancées immédiatement.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except give_up_on:
                    raise
                except exceptions as exc:
                    last_error = exc
                    if attempt == attempts:
                        break
                    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                    delay += random.uniform(0, delay * 0.25)  # jitter anti-thundering-herd
                    logger.warning(
                        "%s a échoué (tentative %s/%s) : %s — nouvelle tentative dans %.1fs",
                        func.__name__, attempt, attempts, exc, delay,
                    )
                    sleep_fn(delay)
            assert last_error is not None
            raise last_error

        return wrapper

    return decorator


def safe_call(func: Callable[..., T], *args, default: T = None, label: str = "", **kwargs) -> T:
    """Exécute `func` en avalant toute exception : renvoie `default` en cas d'échec.

    Utilisé pour les sources de veille : une source morte ne doit jamais empêcher
    le pipeline de tourner avec les autres.
    """
    try:
        return func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - dégradation gracieuse volontaire
        logger.warning("Appel non critique en échec%s : %s", f" ({label})" if label else "", exc)
        return default
