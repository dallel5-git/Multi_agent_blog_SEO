"""Test bout-en-bout du pilotage en mode hors ligne (Lot 7, issue #82).

Équivalent de `test_cli_dry_run_offline.py` côté blogseo : un run complet,
sans clé ni réseau — mais VÉRIFIÉ, pas supposé. `requests.get`/`requests.post`
sont remplacés par une sonde qui lève si elle est appelée : si un pipeline se
mettait un jour à appeler le réseau malgré `--offline`, ce test échouerait au
lieu de rester silencieusement optimiste.

`make offline-pilotage` lance ce fichier (voir Makefile).
"""

from __future__ import annotations

import time

import pytest
import requests

from pilotage import cli
from pilotage.platforms import Platform


class _AppelReseauInattendu(AssertionError):
    """Levée si du code hors ligne tente malgré tout un appel réseau."""


@pytest.fixture
def offline_env(tmp_path, monkeypatch):
    """Base SQLite jetable (créée dans `tmp_path`, détruite avec lui — aucune
    base préexistante requise), coupée de toute clé d'API, réseau interdit.

    Neutralise `_load_dotenv()` : sans ça, `PilotageSettings.from_env()`
    relirait le vrai `.env` du projet et repeuplerait les clés qu'on vient
    d'effacer (même piège que `test_settings.py::clean_env`)."""
    import pilotage.config.settings as settings_module

    monkeypatch.setattr(settings_module, "_load_dotenv", lambda: None)

    db_path = tmp_path / "calendar.db"
    monkeypatch.setenv("PILOTAGE_DB_PATH", str(db_path))
    monkeypatch.setenv("BLOG_CONTENT_DIR", str(tmp_path / "blog_absent"))

    for key in (
        "GROQ_API_KEY", "YOUTUBE_API_KEY", "META_PAGE_ACCESS_TOKEN",
        "PILOTAGE_YOUTUBE_BOT_TOKEN", "PILOTAGE_YOUTUBE_CHAT_ID",
        "PILOTAGE_TIKTOK_BOT_TOKEN", "PILOTAGE_TIKTOK_CHAT_ID",
        "PILOTAGE_INSTAGRAM_BOT_TOKEN", "PILOTAGE_INSTAGRAM_CHAT_ID",
        "PILOTAGE_X_BOT_TOKEN", "PILOTAGE_X_CHAT_ID",
        "PILOTAGE_FACEBOOK_BOT_TOKEN", "PILOTAGE_FACEBOOK_CHAT_ID",
        "PILOTAGE_TELEGRAM_CHANNEL_BOT_TOKEN", "PILOTAGE_TELEGRAM_CHANNEL_CHAT_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    def _interdit(*args, **kwargs):
        raise _AppelReseauInattendu(f"appel réseau inattendu en mode hors ligne : {args!r} {kwargs!r}")

    monkeypatch.setattr(requests, "get", _interdit)
    monkeypatch.setattr(requests, "post", _interdit)

    return db_path


def test_offline_pilotage_migre_et_lance_les_six_pipelines_sans_reseau(offline_env):
    assert cli.main(["migrate"]) == cli.EXIT_OK

    debut = time.monotonic()
    for platform in Platform.piloted():
        exit_code = cli.main(["run", platform.value, "--offline"])
        assert exit_code == cli.EXIT_OK, f"échec pour {platform.value}"
    duree = time.monotonic() - debut

    assert duree < 30, f"trop lent pour un mode hors ligne : {duree:.1f}s"


def test_offline_pilotage_produit_un_brouillon_par_plateforme(offline_env):
    from pilotage.config.settings import PilotageSettings
    from pilotage.shared_calendar.models import ContentStatus
    from pilotage.shared_calendar.repository import CalendarRepository

    cli.main(["migrate"])
    for platform in Platform.piloted():
        cli.main(["run", platform.value, "--offline"])

    settings = PilotageSettings.from_env()
    repository = CalendarRepository(settings.calendar.db_path)
    try:
        for platform in Platform.piloted():
            items = repository.list_by_platform(platform)
            assert len(items) == 1, f"{platform.value} : brouillon manquant ou en double"
            assert items[0].status is ContentStatus.DRAFTED
    finally:
        repository.close()


def test_offline_pilotage_ne_necessite_aucune_cle(offline_env, monkeypatch):
    # `offline_env` a déjà retiré GROQ_API_KEY ; on le confirme explicitement
    # pour que ce test reste lisible même si le fixture change un jour.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    cli.main(["migrate"])
    assert cli.main(["run", "youtube", "--offline"]) == cli.EXIT_OK
