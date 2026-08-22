"""Tests du correctif de compatibilité pytrends/urllib3.

`pytrends` 4.9.2 (dernière version publiée) construit son `Retry` avec le
paramètre `method_whitelist`, renommé `allowed_methods` depuis urllib3 2.0.
Sans correctif, tout appel Google Trends échoue silencieusement avec un
`TypeError` (observé en conditions réelles : `pytrends a échoué ... /5
terme(s)`), alors que l'adapter est censé dégrader gracieusement, pas planter
sur un bug tiers évitable.
"""

from __future__ import annotations

from blogseo.infrastructure.trends.pytrends_adapter import _patch_urllib3_method_whitelist


class TestCorrectifMethodWhitelist:
    def test_method_whitelist_ne_leve_plus_apres_correctif(self):
        _patch_urllib3_method_whitelist()
        from urllib3.util.retry import Retry

        # Reproduit exactement l'appel fait par pytrends 4.9.2 (request.py:124-128).
        retry = Retry(total=2, read=2, connect=2, backoff_factor=0.5,
                       method_whitelist=frozenset(["GET", "POST"]))

        assert set(retry.allowed_methods) == {"GET", "POST"}

    def test_appel_sans_method_whitelist_reste_inchange(self):
        _patch_urllib3_method_whitelist()
        from urllib3.util.retry import Retry

        retry = Retry(total=1, allowed_methods=frozenset(["GET"]))

        assert set(retry.allowed_methods) == {"GET"}

    def test_idempotent(self):
        _patch_urllib3_method_whitelist()
        _patch_urllib3_method_whitelist()
        from urllib3.util.retry import Retry

        assert Retry._blogseo_patched is True
