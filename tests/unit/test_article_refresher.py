"""Tests de `MdxArticleRefresher` : réécriture ciblée titre/description (issue #42).

Règle centrale à vérifier : seuls `title`/`description` changent dans le
frontmatter, le corps et le nom de fichier (donc le slug) restent identiques.
"""

from __future__ import annotations

import pytest

from blogseo.domain.errors import PublicationError
from blogseo.infrastructure.persistence.mdx_article_source import parse_frontmatter
from blogseo.infrastructure.publishing.article_refresher import MdxArticleRefresher


@pytest.fixture
def blog_dir(tmp_path, article):
    (tmp_path / article.slug.filename).write_text(article.to_mdx(), encoding="utf-8")
    return tmp_path


class TestLecture:
    def test_relit_le_titre_la_description_et_le_corps(self, blog_dir, article):
        refresher = MdxArticleRefresher(blog_dir)

        existing = refresher.read(article.slug.value)

        assert existing is not None
        assert existing.slug == article.slug.value
        assert existing.title == article.seo.meta_title
        assert existing.description == article.seo.meta_description
        assert existing.category == article.category.value
        assert existing.body_markdown.strip() == article.body_markdown.strip()

    def test_slug_introuvable_renvoie_none(self, blog_dir):
        refresher = MdxArticleRefresher(blog_dir)
        assert refresher.read("slug-inexistant") is None


class TestMiseAJour:
    def test_remplace_uniquement_titre_et_description(self, blog_dir, article):
        refresher = MdxArticleRefresher(blog_dir)

        path = refresher.update_metadata(
            article.slug.value,
            title="Nouveau titre optimisé pour le CTR",
            description="Nouvelle description plus incitative au clic pour cet article.",
        )

        assert path == blog_dir / article.slug.filename
        raw = path.read_text(encoding="utf-8")
        front = parse_frontmatter(raw)
        assert front["title"] == "Nouveau titre optimisé pour le CTR"
        assert front["description"] == "Nouvelle description plus incitative au clic pour cet article."
        # Rien d'autre ne bouge : ni le corps, ni le reste du frontmatter, ni le nom de fichier.
        assert front["category"] == article.category.value
        assert list(blog_dir.glob("*.mdx")) == [blog_dir / article.slug.filename]
        body_after = raw.split("---", 2)[2].strip()
        assert body_after == article.body_markdown.strip()

    def test_echappe_les_guillemets_dans_les_nouvelles_valeurs(self, blog_dir, article):
        refresher = MdxArticleRefresher(blog_dir)

        path = refresher.update_metadata(
            article.slug.value,
            title='Le titre "spécial" avec guillemets',
            description="Description normale.",
        )

        front = parse_frontmatter(path.read_text(encoding="utf-8"))
        assert front["title"] == 'Le titre "spécial" avec guillemets'

    def test_slug_introuvable_renvoie_none(self, blog_dir):
        refresher = MdxArticleRefresher(blog_dir)
        result = refresher.update_metadata("slug-inexistant", title="x", description="y")
        assert result is None

    def test_aucun_fichier_temporaire_ne_subsiste(self, blog_dir, article):
        refresher = MdxArticleRefresher(blog_dir)
        refresher.update_metadata(article.slug.value, title="Titre", description="Description.")
        assert list(blog_dir.glob("*.tmp")) == []

    def test_frontmatter_absent_leve_une_erreur(self, tmp_path):
        path = tmp_path / "sans-frontmatter.mdx"
        path.write_text("# Juste du contenu, sans frontmatter\n", encoding="utf-8")
        refresher = MdxArticleRefresher(tmp_path)

        with pytest.raises(PublicationError):
            refresher.update_metadata("sans-frontmatter", title="x", description="y")
