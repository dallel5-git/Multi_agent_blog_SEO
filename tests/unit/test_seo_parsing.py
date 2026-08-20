"""Tests du parsing et de la validation SEO : métadonnées, frontmatter, JSON du LLM."""

from __future__ import annotations

import pytest

from blogseo.domain.value_objects.category import Category
from blogseo.domain.value_objects.seo_metadata import SeoMetadata
from blogseo.infrastructure.persistence.mdx_article_source import parse_frontmatter
from blogseo.shared.json_utils import extract_json
from blogseo.shared.text import extract_urls, strip_frontmatter, truncate


class TestSeoMetadata:
    def test_metadonnees_conformes(self, seo):
        assert seo.is_valid, seo.all_issues()

    def test_titre_trop_court(self):
        meta = SeoMetadata(meta_title="n8n", meta_description="x" * 130, focus_keyword="n8n")
        assert any("trop court" in issue for issue in meta.title_issues())

    def test_titre_trop_long(self):
        meta = SeoMetadata(meta_title="a" * 90, meta_description="x" * 130, focus_keyword="a")
        assert any("trop long" in issue for issue in meta.title_issues())

    def test_titre_sans_mot_cle(self):
        meta = SeoMetadata(
            meta_title="Un titre parfaitement calibré pour Google ici",
            meta_description="x" * 130,
            focus_keyword="introuvable",
        )
        assert any("mot-clé" in issue for issue in meta.title_issues())

    def test_description_hors_bornes(self):
        meta = SeoMetadata(meta_title="Titre correct de longueur acceptable", meta_description="court",
                           focus_keyword="titre")
        assert meta.description_issues()

    def test_tous_les_mots_cles(self, seo):
        assert seo.all_keywords[0] == seo.focus_keyword
        assert "n8n Tunisie" in seo.all_keywords


class TestCategory:
    @pytest.mark.parametrize(
        "brut,attendu",
        [
            ("n8n", Category.N8N), ("N8N", Category.N8N), ("Make", Category.MAKE),
            ("agents ia", Category.AGENTS_IA), ("Agents IA", Category.AGENTS_IA),
            ("python", Category.PYTHON), ("intelligence artificielle", Category.IA),
            ("integromat", Category.MAKE), ("nocode", Category.MAKE),
        ],
    )
    def test_normalisation(self, brut, attendu):
        assert Category.coerce(brut) is attendu

    def test_valeur_inconnue_retombe_sur_le_defaut(self):
        assert Category.coerce("Blockchain") is Category.IA
        assert Category.coerce(None) is Category.IA

    def test_toutes_les_valeurs_sont_celles_du_site(self):
        assert Category.values() == ["IA", "n8n", "Make", "Python", "Agents IA"]


class TestFrontmatter:
    RAW = '''---
title: "Créer un agent IA"
description: "Un guide complet"
date: "2026-08-05"
category: "Agents IA"
tags: ["python", "agents", "ia"]
coverImage: ""
featured: true
---

Le corps de l'article.
'''

    def test_extraction_des_champs(self):
        data = parse_frontmatter(self.RAW)
        assert data["title"] == "Créer un agent IA"
        assert data["category"] == "Agents IA"
        assert data["tags"] == ["python", "agents", "ia"]
        assert data["featured"] is True

    def test_absence_de_frontmatter(self):
        assert parse_frontmatter("Juste du texte") == {}

    def test_serialisation_puis_relecture(self, article):
        """Le .mdx produit doit être relisible par le parseur du blog."""
        data = parse_frontmatter(article.to_mdx())
        assert data["title"] == article.seo.meta_title
        assert data["category"] == article.category.value
        assert data["date"] == "2026-08-19"
        assert data["tags"] == list(article.tags)

    def test_les_guillemets_sont_echappes(self, article):
        article.seo = SeoMetadata(
            meta_title='Le guide "ultime" de n8n en Tunisie aujourd\'hui',
            meta_description="d" * 130,
            focus_keyword="n8n",
        )
        data = parse_frontmatter(article.to_mdx())
        assert data["title"] == 'Le guide "ultime" de n8n en Tunisie aujourd\'hui'


class TestExtractionJsonDuLLM:
    def test_json_nu(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_dans_un_bloc_de_code(self):
        assert extract_json('Voici :\n```json\n{"a": 1}\n```\nVoilà.') == {"a": 1}

    def test_json_entoure_de_bavardage(self):
        assert extract_json('Bien sûr ! {"titre": "test"} J\'espère que ça aide.') == {"titre": "test"}

    def test_virgule_finale_toleree(self):
        assert extract_json('{"a": 1, "b": 2,}') == {"a": 2 - 1, "b": 2}

    def test_objet_imbrique(self):
        data = extract_json('{"k": {"term": "n8n", "intent": "tutorial"}}')
        assert data["k"]["term"] == "n8n"

    def test_liste_racine_est_enveloppee(self):
        assert extract_json("[1, 2, 3]") == {"items": [1, 2, 3]}

    def test_defaut_si_illisible(self):
        assert extract_json("pas du json", default={"vide": True}) == {"vide": True}

    def test_leve_sans_defaut(self):
        with pytest.raises(ValueError):
            extract_json("pas du json du tout")

    def test_accolade_dans_une_chaine(self):
        assert extract_json('{"code": "if (x) { y }"}')["code"] == "if (x) { y }"


class TestUtilitairesTexte:
    def test_troncature_sur_frontiere_de_mot(self):
        assert truncate("un deux trois quatre", 12).endswith("…")
        assert "quatr" not in truncate("un deux trois quatre", 12)

    def test_pas_de_troncature_si_assez_court(self):
        assert truncate("court", 50) == "court"

    def test_extraction_des_urls(self):
        texte = "Voir [n8n](https://n8n.io) et https://example.com/page, puis la suite."
        urls = extract_urls(texte)
        assert "https://n8n.io" in urls
        assert "https://example.com/page" in urls

    def test_suppression_du_frontmatter_parasite(self):
        assert strip_frontmatter("---\ntitle: x\n---\n\nLe corps.").strip() == "Le corps."

    def test_corps_sans_frontmatter_inchange(self):
        assert strip_frontmatter("Le corps.") == "Le corps."
