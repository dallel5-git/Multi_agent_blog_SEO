"""Tests de l'entité `Article` : mesures et sérialisation MDX."""

from __future__ import annotations

from datetime import date

from blogseo.domain.entities.article import Article
from blogseo.domain.value_objects.category import Category
from blogseo.domain.value_objects.seo_metadata import SeoMetadata
from blogseo.domain.value_objects.slug import Slug


class TestMesures:
    def test_le_code_n_est_pas_compte_dans_les_mots(self, article):
        avant = article.word_count
        article.body_markdown += "\n\n```python\n" + "x = 1\n" * 200 + "```\n"
        assert article.word_count == avant

    def test_comptage_des_h2(self, article):
        assert article.h2_count >= 4

    def test_detection_des_titres(self):
        art = _minimal("## Une\n\ntexte\n\n### Deux\n\ntexte")
        assert art.headings == [(2, "Une"), (3, "Deux")]

    def test_blocs_de_code_equilibres(self):
        assert _minimal("```python\nx=1\n```").has_balanced_code_fences
        assert not _minimal("```python\nx=1\n").has_balanced_code_fences

    def test_densite_de_mot_cle(self):
        art = _minimal("n8n " * 10 + "mot " * 90)
        assert art.keyword_density("n8n") == 0.1

    def test_densite_nulle_si_mot_cle_vide(self, article):
        assert article.keyword_density("") == 0.0


class TestSerialisationMdx:
    def test_le_frontmatter_contient_tous_les_champs_du_site(self, article):
        front = article.to_frontmatter()
        for champ in ("title", "description", "date", "category", "tags",
                      "coverImage", "youtubeUrl", "author", "featured"):
            assert f"{champ}:" in front

    def test_les_tags_sont_une_liste_inline(self, article):
        assert 'tags: ["n8n", "automatisation", "tunisie"]' in article.to_frontmatter()

    def test_le_booleen_featured_n_est_pas_une_chaine(self, article):
        assert "featured: false" in article.to_frontmatter()

    def test_le_document_commence_et_se_termine_proprement(self, article):
        mdx = article.to_mdx()
        assert mdx.startswith("---\n")
        assert mdx.endswith("\n")
        assert mdx.count("\n---\n") >= 1

    def test_le_titre_utilise_le_meta_title(self, article):
        assert article.seo.meta_title in article.to_frontmatter()


class TestCopies:
    def test_with_body_incremente_la_revision(self, article):
        nouveau = article.with_body("## Nouveau corps")
        assert nouveau.revision == article.revision + 1
        assert nouveau.body_markdown == "## Nouveau corps"

    def test_with_seo_remplace_les_metadonnees(self, article):
        seo = SeoMetadata(meta_title="Autre titre suffisamment long ici", meta_description="d" * 130,
                          focus_keyword="autre")
        assert article.with_seo(seo).seo.meta_title == "Autre titre suffisamment long ici"


def _minimal(body: str) -> Article:
    return Article(
        title="T",
        slug=Slug("t"),
        body_markdown=body,
        seo=SeoMetadata(meta_title="T", meta_description="d", focus_keyword="k"),
        category=Category.IA,
        published_on=date(2026, 1, 1),
    )
