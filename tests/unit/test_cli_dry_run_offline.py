"""Tests bout-en-bout de `blogseo run --dry-run --offline --print` (issue #30).

Contrat vérifié :
- `--dry-run --offline` produit un article complet, sans aucune clé ni réseau ;
- le dossier du blog n'est jamais touché en dry-run ;
- `--print` affiche le `.mdx` final dans le terminal, et seulement dans ce cas.
"""

from __future__ import annotations

import pytest

from blogseo.interfaces import cli


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Pipeline pointé sur des dossiers jetables, coupé de toute clé d'API."""
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


class TestDryRunOffline:
    def test_produit_un_article_complet_sans_cle_ni_reseau(self, isolated_env, capsys):
        exit_code = cli.main(["run", "--dry-run", "--offline"])

        assert exit_code == cli.EXIT_OK
        out = capsys.readouterr().out
        assert "RÉSULTAT" in out
        assert "Aucun article produit." not in out
        assert "Qualité" in out

    def test_le_dossier_du_blog_n_est_jamais_touche(self, isolated_env):
        blog_repo, blog_content, storage = isolated_env

        cli.main(["run", "--dry-run", "--offline"])

        assert list(blog_content.iterdir()) == []
        assert list(storage.glob("drafts/*.mdx")), "le brouillon doit malgré tout être écrit"

    def test_aucun_commit_ni_push_en_dry_run(self, isolated_env):
        blog_repo, _, _ = isolated_env

        cli.main(["run", "--dry-run", "--offline"])

        # Le dépôt du blog n'a même pas été initialisé par le pipeline.
        assert not (blog_repo / ".git").exists()


class TestOptionPrint:
    def test_print_affiche_le_mdx_complet(self, isolated_env, capsys):
        cli.main(["run", "--dry-run", "--offline", "--print"])

        out = capsys.readouterr().out
        assert "\n---\n" in out  # bornes du frontmatter YAML de l'article
        assert "meta_title" in out or "title:" in out

    def test_sans_l_option_le_mdx_n_est_pas_affiche(self, isolated_env, capsys):
        cli.main(["run", "--dry-run", "--offline"])

        out = capsys.readouterr().out
        assert "\n---\n" not in out
