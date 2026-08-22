"""Tests de `Settings` : parsing des variables d'environnement et `describe()`.

`describe()` porte une garantie de sécurité explicite (ARCHITECTURE.md §6) :
elle n'affiche jamais une clé d'API en clair, seulement « configurée » /
« absente ». C'est le seul test qui la vérifie directement.
"""

from __future__ import annotations

from blogseo.infrastructure.config.settings import (
    Settings,
    _env_bool,
    _env_float,
    _env_int,
    _env_list,
)

# Toutes les clés lues par `Settings.from_env()` qui pourraient être définies
# dans le `.env` réel du projet : on les efface pour des tests hermétiques,
# indépendants de la machine sur laquelle ils tournent.
_ENV_KEYS = (
    "GROQ_API_KEY", "GROQ_MODEL", "OPENROUTER_API_KEY", "GEMINI_API_KEY",
    "CEREBRAS_API_KEY", "TAVILY_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "HUMAN_REVIEW", "ORCHESTRATOR", "LOG_LEVEL", "DRY_RUN", "STORAGE_DIR",
    "BLOG_CONTENT_DIR", "BLOG_REPO_DIR",
)


def clean_env(monkeypatch):
    """Isole `Settings.from_env()` de la machine locale.

    `_load_dotenv()` relit le vrai `.env` du projet (avec de vraies clés) dès
    qu'une variable est absente de `os.environ` — sans ce court-circuit, un
    simple `monkeypatch.delenv` ne suffit pas à obtenir un état par défaut
    déterministe : `.env` le repeuplerait aussitôt.
    """
    import blogseo.infrastructure.config.settings as settings_module

    monkeypatch.setattr(settings_module, "_load_dotenv", lambda: None)
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestHelpersEnv:
    def test_env_bool_accepte_plusieurs_formes_de_vrai(self, monkeypatch):
        for value in ("1", "true", "True", "yes", "on", "oui"):
            monkeypatch.setenv("X_BOOL", value)
            assert _env_bool("X_BOOL", False) is True

    def test_env_bool_faux_par_defaut(self, monkeypatch):
        monkeypatch.setenv("X_BOOL", "n'importe quoi")
        assert _env_bool("X_BOOL", False) is False

    def test_env_bool_absent_retombe_sur_le_defaut(self, monkeypatch):
        monkeypatch.delenv("X_BOOL", raising=False)
        assert _env_bool("X_BOOL", True) is True
        assert _env_bool("X_BOOL", False) is False

    def test_env_int_valide(self, monkeypatch):
        monkeypatch.setenv("X_INT", "42")
        assert _env_int("X_INT", 0) == 42

    def test_env_int_invalide_retombe_sur_le_defaut(self, monkeypatch):
        monkeypatch.setenv("X_INT", "pas un nombre")
        assert _env_int("X_INT", 7) == 7

    def test_env_float_invalide_retombe_sur_le_defaut(self, monkeypatch):
        monkeypatch.setenv("X_FLOAT", "abc")
        assert _env_float("X_FLOAT", 1.5) == 1.5

    def test_env_list_separe_sur_les_virgules_et_nettoie_les_espaces(self, monkeypatch):
        monkeypatch.setenv("X_LIST", "a, b ,  c")
        assert _env_list("X_LIST") == ("a", "b", "c")

    def test_env_list_absent_utilise_le_defaut(self, monkeypatch):
        monkeypatch.delenv("X_LIST", raising=False)
        assert _env_list("X_LIST", "x,y") == ("x", "y")


class TestSettingsFromEnv:
    def test_valeurs_par_defaut_sans_variables_definies(self, monkeypatch):
        clean_env(monkeypatch)
        settings = Settings.from_env()

        assert settings.human_review is True
        assert settings.orchestrator == "langgraph"
        assert settings.log_level == "INFO"
        assert settings.llm.groq_model == "openai/gpt-oss-20b"
        assert not settings.llm.has_any_provider

    def test_les_variables_d_environnement_l_emportent(self, monkeypatch):
        clean_env(monkeypatch)
        monkeypatch.setenv("HUMAN_REVIEW", "false")
        monkeypatch.setenv("ORCHESTRATOR", "SEQUENTIAL")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")

        settings = Settings.from_env()

        assert settings.human_review is False
        assert settings.orchestrator == "sequential"  # normalisé en minuscules
        assert settings.llm.groq_api_key == "gsk_test_key"
        assert settings.llm.has_any_provider

    def test_chemins_du_blog_sont_expanduser(self, monkeypatch):
        clean_env(monkeypatch)
        monkeypatch.setenv("BLOG_CONTENT_DIR", "~/mon-blog/content")

        settings = Settings.from_env()

        assert "~" not in str(settings.publishing.blog_content_dir)


class TestDescribeNeDivulguePasLesCles:
    def test_les_cles_reelles_n_apparaissent_jamais_dans_describe(self, monkeypatch):
        clean_env(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "gsk_secret_de_test_123")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secret-de-test-456")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:AAFsecretdetesttoken")

        settings = Settings.from_env()
        output = settings.describe()

        assert "gsk_secret_de_test_123" not in output
        assert "sk-or-secret-de-test-456" not in output
        assert "123456789:AAFsecretdetesttoken" not in output
        assert "✅ configurée" in output

    def test_absence_de_cle_est_signalee(self, monkeypatch):
        clean_env(monkeypatch)
        settings = Settings.from_env()

        assert "❌ absente" in settings.describe()
