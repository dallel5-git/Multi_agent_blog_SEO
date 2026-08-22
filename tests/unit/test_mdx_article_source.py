"""Tests de `MdxArticleSource` (lecture des articles publiés depuis le disque).

Le parsing du frontmatter lui-même est couvert par `test_seo_parsing.py` ;
ici on teste le comportement de la classe : glob, tri, tolérance aux fichiers
illisibles ou au dossier absent.
"""

from __future__ import annotations

from blogseo.infrastructure.persistence.mdx_article_source import MdxArticleSource

ARTICLE_MDX = """---
title: "{title}"
description: "Une description correcte."
date: "2026-08-19"
category: "n8n"
tags: ["n8n", "automatisation"]
---

Le corps de l'article.
"""


def write_article(directory, slug: str, title: str) -> None:
    (directory / f"{slug}.mdx").write_text(ARTICLE_MDX.format(title=title), encoding="utf-8")


class TestListPublished:
    def test_liste_tous_les_articles_du_dossier(self, tmp_path):
        write_article(tmp_path, "premier-article", "Premier article")
        write_article(tmp_path, "second-article", "Second article")
        source = MdxArticleSource(tmp_path)

        refs = source.list_published()

        assert {r.slug for r in refs} == {"premier-article", "second-article"}
        assert all(r.category == "n8n" for r in refs)
        assert all(r.tags == ("n8n", "automatisation") for r in refs)

    def test_dossier_absent_renvoie_une_liste_vide(self, tmp_path):
        source = MdxArticleSource(tmp_path / "n-existe-pas")
        assert source.list_published() == []

    def test_dossier_vide_renvoie_une_liste_vide(self, tmp_path):
        source = MdxArticleSource(tmp_path)
        assert source.list_published() == []

    def test_fichier_illisible_est_ignore_sans_planter(self, tmp_path):
        write_article(tmp_path, "bon-article", "Bon article")
        bad = tmp_path / "illisible.mdx"
        bad.write_text("contenu", encoding="utf-8")
        bad.chmod(0o000)
        try:
            source = MdxArticleSource(tmp_path)
            refs = source.list_published()
        finally:
            bad.chmod(0o644)  # pour que pytest puisse nettoyer tmp_path

        assert "bon-article" in {r.slug for r in refs}

    def test_ignore_les_fichiers_non_mdx(self, tmp_path):
        write_article(tmp_path, "un-article", "Un article")
        (tmp_path / "notes.txt").write_text("pas un article", encoding="utf-8")

        source = MdxArticleSource(tmp_path)

        assert {r.slug for r in source.list_published()} == {"un-article"}


class TestSlugs:
    def test_renvoie_l_ensemble_des_slugs(self, tmp_path):
        write_article(tmp_path, "premier", "Premier")
        write_article(tmp_path, "second", "Second")
        source = MdxArticleSource(tmp_path)

        assert source.slugs() == {"premier", "second"}

    def test_dossier_absent_renvoie_un_ensemble_vide(self, tmp_path):
        source = MdxArticleSource(tmp_path / "n-existe-pas")
        assert source.slugs() == set()
