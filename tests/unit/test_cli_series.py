"""Tests bout-en-bout de `blogseo series start/list/show` (issue #41)."""

from __future__ import annotations

import pytest

from blogseo.interfaces import cli


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    blog_repo = tmp_path / "blog"
    blog_content = blog_repo / "content" / "articles"
    blog_content.mkdir(parents=True)
    storage = tmp_path / "storage"

    for key in (
        "CEREBRAS_API_KEY", "GROQ_API_KEY", "TAVILY_API_KEY",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BLOG_CONTENT_DIR", str(blog_content))
    monkeypatch.setenv("BLOG_REPO_DIR", str(blog_repo))
    monkeypatch.setenv("STORAGE_DIR", str(storage))

    return blog_repo, blog_content, storage


class TestSeriesStart:
    def test_planifie_et_affiche_le_bon_nombre_de_sujets(self, isolated_env, capsys):
        exit_code = cli.main(["series", "start", "Automatiser sa PME avec n8n", "--size", "3", "--offline"])

        assert exit_code == cli.EXIT_OK
        out = capsys.readouterr().out
        assert "3/3" not in out  # rien n'est encore publié
        assert "  1." in out and "  2." in out and "  3." in out

    def test_persiste_la_serie_sur_disque(self, isolated_env):
        _, _, storage = isolated_env

        cli.main(["series", "start", "Automatiser sa PME avec n8n", "--size", "3", "--offline"])

        assert list((storage / "series").glob("*.json"))

    def test_taille_hors_bornes_est_refusee(self, isolated_env, capsys):
        exit_code = cli.main(["series", "start", "Thème", "--size", "8", "--offline"])

        assert exit_code == cli.EXIT_ERROR
        assert "3 et 5" in capsys.readouterr().out


class TestSeriesListEtShow:
    def test_list_est_vide_sans_serie(self, isolated_env, capsys):
        exit_code = cli.main(["series", "list"])

        assert exit_code == cli.EXIT_OK
        assert "Aucune série" in capsys.readouterr().out

    def test_list_puis_show_apres_planification(self, isolated_env, capsys):
        cli.main(["series", "start", "Automatiser sa PME avec n8n", "--size", "3", "--offline"])
        capsys.readouterr()  # purge la sortie de `start`

        assert cli.main(["series", "list"]) == cli.EXIT_OK
        listed = capsys.readouterr().out
        assert "active" in listed

        series_id = listed.split("\n")[3].split()[0]
        assert cli.main(["series", "show", series_id]) == cli.EXIT_OK
        detail = capsys.readouterr().out
        assert "pending" in detail

    def test_show_id_inconnu(self, isolated_env, capsys):
        exit_code = cli.main(["series", "show", "serie-inconnue"])

        assert exit_code == cli.EXIT_ERROR
        assert "introuvable" in capsys.readouterr().out
