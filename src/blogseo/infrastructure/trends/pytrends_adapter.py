"""Adapter Google Trends via `pytrends` (gratuit, sans clé).

Google Trends bloque régulièrement les IP qui interrogent trop vite (HTTP 429).
L'adapter dégrade donc silencieusement : en cas d'échec, il renvoie un
dictionnaire vide et le Keyword Analyst travaille sans ce signal.
"""

from __future__ import annotations

import inspect
import logging
import time

from ...domain.ports.search import TrendsPort

logger = logging.getLogger(__name__)


def _patch_urllib3_method_whitelist() -> None:
    """Corrige une incompatibilité pytrends/urllib3 (pas un bug de ce projet).

    `pytrends` 4.9.2 (la dernière version publiée) construit encore son
    `Retry(method_whitelist=...)` avec l'ancien nom de paramètre, renommé
    `allowed_methods` depuis urllib3 2.0. Sans correctif, tout appel Google
    Trends échoue avec `TypeError: unexpected keyword argument
    'method_whitelist'` — dégradation silencieuse (voir résilience §5), mais
    évitable sans nouvelle dépendance ni version épinglée : on traduit le
    paramètre à la volée, uniquement si l'installation d'urllib3 en a besoin.
    """
    try:
        from urllib3.util.retry import Retry
    except ImportError:
        return

    if getattr(Retry, "_blogseo_patched", False):
        return
    if "method_whitelist" in inspect.signature(Retry.__init__).parameters:
        return  # urllib3 < 2.0 : le paramètre existe déjà, rien à faire

    original_init = Retry.__init__

    def patched_init(self, *args, method_whitelist=None, **kwargs):
        if method_whitelist is not None:
            kwargs.setdefault("allowed_methods", method_whitelist)
        original_init(self, *args, **kwargs)

    Retry.__init__ = patched_init
    Retry._blogseo_patched = True


class PyTrendsAdapter(TrendsPort):
    """Intérêt de recherche et requêtes associées, géolocalisés Tunisie par défaut."""

    name = "pytrends"

    def __init__(self, *, hl: str = "fr-FR", tz: int = 60, delay_s: float = 2.0) -> None:
        self.hl = hl
        self.tz = tz  # UTC+1 : fuseau de Tunis
        self.delay_s = delay_s
        self._client = None
        self._unavailable = False

    def _get_client(self):
        if self._client is not None or self._unavailable:
            return self._client
        try:
            from pytrends.request import TrendReq  # type: ignore[import-not-found]

            _patch_urllib3_method_whitelist()
            self._client = TrendReq(hl=self.hl, tz=self.tz, timeout=(10, 25), retries=2, backoff_factor=0.5)
        except ImportError:
            logger.warning("pytrends non installé : le signal Google Trends sera ignoré")
            self._unavailable = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("pytrends indisponible : %s", exc)
            self._unavailable = True
        return self._client

    def is_available(self) -> bool:
        return self._get_client() is not None

    # ------------------------------------------------------------------ #
    def interest_over_time(self, keywords: list[str], *, geo: str = "TN", timeframe: str = "now 7-d") -> dict[str, float]:
        client = self._get_client()
        if client is None or not keywords:
            return {}

        # Google Trends n'accepte que 5 termes par requête.
        scores: dict[str, float] = {}
        for chunk_start in range(0, len(keywords), 5):
            chunk = keywords[chunk_start : chunk_start + 5]
            try:
                client.build_payload(chunk, cat=0, timeframe=timeframe, geo=geo, gprop="")
                frame = client.interest_over_time()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Google Trends a échoué pour %s : %s", chunk, exc)
                continue
            if frame is None or frame.empty:
                continue
            for term in chunk:
                if term in frame.columns:
                    scores[term] = round(float(frame[term].mean()), 2)
            time.sleep(self.delay_s)

        logger.info("[pytrends] intérêt calculé pour %s/%s terme(s) (geo=%s)", len(scores), len(keywords), geo)
        return scores

    def related_queries(self, keyword: str, *, geo: str = "TN") -> list[str]:
        client = self._get_client()
        if client is None:
            return []
        try:
            client.build_payload([keyword], cat=0, timeframe="today 3-m", geo=geo, gprop="")
            related = client.related_queries() or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Google Trends (requêtes associées) a échoué pour « %s » : %s", keyword, exc)
            return []

        bucket = related.get(keyword) or {}
        terms: list[str] = []
        for key in ("rising", "top"):
            frame = bucket.get(key)
            if frame is not None and not frame.empty and "query" in frame.columns:
                terms.extend(frame["query"].head(10).tolist())

        seen: set[str] = set()
        unique = [t for t in terms if not (t in seen or seen.add(t))]
        logger.info("[pytrends] %s requête(s) associée(s) à « %s »", len(unique), keyword)
        return unique
