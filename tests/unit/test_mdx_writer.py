"""Tests de `MdxArticleWriter` : écriture atomique et anti-écrasement.

Fait partie d'EPIC 5 (issue #27) : « Aucun article ne part en ligne sans un
clic humain », ce qui suppose aussi que le fichier écrit soit toujours
complet (jamais lu à moitié par Next.js) et qu'un slug existant ne soit
jamais silencieusement écrasé.
"""

from __future__ import annotations

from blogseo.infrastructure.publishing.mdx_writer import MdxArticleWriter


class TestEcritureDeBase:
    def test_ecrit_le_contenu_mdx_de_l_article(self, tmp_path, article):
        writer = MdxArticleWriter(tmp_path)

        result = writer.write(article)

        assert result.path == tmp_path / "automatiser-prospection-n8n.mdx"
        assert result.path.read_text(encoding="utf-8") == article.to_mdx()
        assert result.bytes_written == len(article.to_mdx().encode("utf-8"))
        assert result.overwritten is False

    def test_cree_le_dossier_de_destination_si_absent(self, tmp_path, article):
        target = tmp_path / "n'existe" / "pas" / "encore"
        writer = MdxArticleWriter(tmp_path)

        writer.write(article, destination=target)

        assert (target / "automatiser-prospection-n8n.mdx").exists()

    def test_aucun_fichier_temporaire_ne_subsiste_apres_l_ecriture(self, tmp_path, article):
        writer = MdxArticleWriter(tmp_path)

        writer.write(article)

        assert list(tmp_path.glob("*.tmp")) == []


class TestAntiEcrasement:
    def test_un_slug_deja_present_est_suffixe_par_la_date_plutot_qu_ecrase(self, tmp_path, article):
        existing = tmp_path / "automatiser-prospection-n8n.mdx"
        existing.write_text("contenu publié existant, ne pas toucher", encoding="utf-8")
        writer = MdxArticleWriter(tmp_path)

        result = writer.write(article, overwrite=False)

        assert existing.read_text(encoding="utf-8") == "contenu publié existant, ne pas toucher"
        assert result.path != existing
        assert result.path.name.startswith("automatiser-prospection-n8n-")
        assert result.path.read_text(encoding="utf-8") == article.to_mdx()

    def test_overwrite_explicite_remplace_le_fichier(self, tmp_path, article):
        existing = tmp_path / "automatiser-prospection-n8n.mdx"
        existing.write_text("ancienne version", encoding="utf-8")
        writer = MdxArticleWriter(tmp_path)

        result = writer.write(article, overwrite=True)

        assert result.path == existing
        assert result.overwritten is True
        assert existing.read_text(encoding="utf-8") == article.to_mdx()
