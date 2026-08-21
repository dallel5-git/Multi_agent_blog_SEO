"""Tests de `GitPublisher` : ajout ciblé (jamais `git add -A`), commit, push.

Fait partie d'EPIC 5 (issue #27) : le chemin ✅ « Publier » ne doit jamais
emporter le travail en cours de l'auteur, et un push refusé ne doit jamais
faire perdre le commit local.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from blogseo.domain.errors import PublicationError
from blogseo.infrastructure.publishing.git_publisher import GitPublisher


def _git(repo_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path) -> Path:
    repo_dir = tmp_path / "repo"
    remote_dir = tmp_path / "remote.git"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(remote_dir)], check=True)
    _git(repo_dir, "remote", "add", "origin", str(remote_dir))
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "test")
    (repo_dir / "README.md").write_text("dépôt de test\n", encoding="utf-8")
    _git(repo_dir, "add", "README.md")
    _git(repo_dir, "commit", "-q", "-m", "commit initial")
    return repo_dir


class TestAjoutCible:
    def test_ne_commite_que_les_fichiers_passes_jamais_add_dash_a(self, repo):
        (repo / "article.mdx").write_text("# contenu de l'article", encoding="utf-8")
        (repo / "brouillon-en-cours.txt").write_text("travail non lié au pipeline", encoding="utf-8")
        publisher = GitPublisher(repo)

        result = publisher.commit_and_push([repo / "article.mdx"], "content: publie article")

        assert result.committed is True
        assert result.pushed is True
        committed_files = _git(repo, "show", "--stat", "--name-only", "--format=", "HEAD").stdout.split()
        assert committed_files == ["article.mdx"]
        # Le fichier étranger au pipeline reste non suivi, jamais emporté.
        status = _git(repo, "status", "--porcelain").stdout
        assert "?? brouillon-en-cours.txt" in status

    def test_un_chemin_hors_du_depot_leve_une_erreur_explicite(self, repo, tmp_path):
        outside = tmp_path / "ailleurs.mdx"
        outside.write_text("hors dépôt", encoding="utf-8")
        publisher = GitPublisher(repo)

        with pytest.raises(PublicationError):
            publisher.commit_and_push([outside], "content: ne doit pas passer")

    def test_contenu_identique_ne_produit_aucun_commit(self, repo):
        (repo / "article.mdx").write_text("stable", encoding="utf-8")
        publisher = GitPublisher(repo)
        publisher.commit_and_push([repo / "article.mdx"], "content: premier commit")
        before = _git(repo, "rev-parse", "HEAD").stdout.strip()

        result = publisher.commit_and_push([repo / "article.mdx"], "content: rien de neuf")

        assert result.committed is False
        assert _git(repo, "rev-parse", "HEAD").stdout.strip() == before


class TestPush:
    def test_push_reussi_atteint_le_remote(self, repo, tmp_path):
        (repo / "article.mdx").write_text("nouvel article", encoding="utf-8")
        publisher = GitPublisher(repo)

        result = publisher.commit_and_push([repo / "article.mdx"], "content: nouvel article")

        assert result.pushed is True
        assert result.commit_sha
        remote_dir = tmp_path / "remote.git"
        remote_log = subprocess.run(
            ["git", "--git-dir", str(remote_dir), "log", "main", "--oneline"],
            capture_output=True, text=True, check=True,
        ).stdout
        assert result.commit_sha in remote_log

    def test_push_refuse_garde_le_commit_local(self, repo):
        (repo / "article.mdx").write_text("article orphelin", encoding="utf-8")
        _git(repo, "remote", "set-url", "origin", "/chemin/git/inexistant.git")
        publisher = GitPublisher(repo)

        result = publisher.commit_and_push([repo / "article.mdx"], "content: push impossible")

        assert result.committed is True
        assert result.pushed is False
        assert result.commit_sha
        # Le commit existe bien localement : rien n'est perdu.
        assert _git(repo, "log", "--oneline", "-1").stdout.strip().startswith(result.commit_sha)


class TestEtatDuDepot:
    def test_is_clean_vrai_sans_modification_pendante(self, repo):
        assert GitPublisher(repo).is_clean() is True

    def test_is_clean_faux_avec_une_modification_pendante(self, repo):
        (repo / "quelque_chose.txt").write_text("non suivi", encoding="utf-8")
        assert GitPublisher(repo).is_clean() is False

    def test_leve_une_erreur_si_le_dossier_n_est_pas_un_depot_git(self, tmp_path):
        not_a_repo = tmp_path / "pas-un-depot"
        not_a_repo.mkdir()
        with pytest.raises(PublicationError):
            GitPublisher(not_a_repo).is_clean()
