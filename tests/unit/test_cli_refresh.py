"""Tests bout-en-bout de `blogseo refresh <slug>` (issue #42).

Critères d'acceptation vérifiés ici au niveau CLI :
- le fichier existant est mis à jour sur place, sans changement de slug ;
- un slug introuvable échoue proprement plutôt que de planter.
"""

from __future__ import annotations

import pytest

from blogseo.interfaces import cli

ARTICLE_MDX = """\
---
title: "Automatiser sa prospection avec n8n"
description: "Ancienne description, peu incitative."
date: "2026-08-01"
category: "n8n"
tags: ["n8n", "automatisation"]
coverImage: ""
youtubeUrl: ""
author: "Oussama Dallel"
featured: false
---

## Introduction

Contenu existant de l'article, jamais modifié par le refresh.
"""


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

    (blog_content / "automatiser-prospection-n8n.mdx").write_text(ARTICLE_MDX, encoding="utf-8")
    return blog_repo, blog_content, storage


class TestRefresh:
    def test_slug_inconnu_echoue_proprement(self, isolated_env, capsys):
        exit_code = cli.main(["refresh", "slug-inconnu", "--offline"])

        assert exit_code == cli.EXIT_ERROR
        assert "Aucun article" in capsys.readouterr().out

    def test_met_a_jour_le_fichier_en_place_sans_changer_le_slug(self, isolated_env, capsys):
        _, blog_content, _ = isolated_env
        path = blog_content / "automatiser-prospection-n8n.mdx"
        original_body = path.read_text(encoding="utf-8").split("---", 2)[2]

        exit_code = cli.main(["refresh", "automatiser-prospection-n8n", "--offline"])

        assert exit_code == cli.EXIT_OK
        assert "RÉGÉNÉRATION" in capsys.readouterr().out
        # Même fichier, même nom : aucun changement de slug.
        assert [p.name for p in blog_content.glob("*.mdx")] == ["automatiser-prospection-n8n.mdx"]
        # Le corps de l'article n'a pas bougé.
        assert path.read_text(encoding="utf-8").split("---", 2)[2] == original_body
