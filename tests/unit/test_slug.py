"""Tests du value object `Slug` (nom de fichier .mdx et URL du blog)."""

from __future__ import annotations

import dataclasses

import pytest

from blogseo.domain.value_objects.slug import Slug


class TestSlugFromTitle:
    def test_supprime_les_accents(self):
        assert Slug.from_title("Créer un agent IA autonome").value == "creer-agent-ia-autonome"

    def test_supprime_les_mots_vides(self):
        slug = Slug.from_title("Le guide de l'automatisation pour les PME")
        assert "de" not in slug.value.split("-")
        assert "les" not in slug.value.split("-")
        assert "guide" in slug.value

    def test_supprime_la_ponctuation(self):
        assert Slug.from_title("Make vs n8n : quel outil choisir ?").value == "make-vs-n8n-quel-outil-choisir"

    def test_tronque_sur_une_frontiere_de_mot(self):
        slug = Slug.from_title("automatiser " * 20, max_length=30)
        assert len(slug.value) <= 30
        assert not slug.value.endswith("-")
        # Aucun mot ne doit être coupé en plein milieu.
        assert all(part == "automatiser" for part in slug.value.split("-"))

    def test_garde_les_mots_vides_si_le_titre_n_en_contient_que(self):
        assert Slug.from_title("Le la les").value == "le-la-les"

    def test_leve_si_le_titre_est_vide(self):
        with pytest.raises(ValueError):
            Slug.from_title("!!! ???")

    def test_est_deterministe(self):
        titre = "Automatiser la prospection avec n8n en Tunisie"
        assert Slug.from_title(titre) == Slug.from_title(titre)


class TestSlugValidation:
    @pytest.mark.parametrize("valeur", ["mon-article", "n8n-2026", "a"])
    def test_accepte_les_slugs_valides(self, valeur):
        assert Slug(valeur).value == valeur

    @pytest.mark.parametrize("valeur", ["Mon-Article", "mon_article", "mon article", "-abc", "abc-", "été"])
    def test_refuse_les_slugs_invalides(self, valeur):
        with pytest.raises(ValueError):
            Slug(valeur)

    def test_filename(self):
        assert Slug("mon-article").filename == "mon-article.mdx"

    def test_est_immuable(self):
        slug = Slug("mon-article")
        # `frozen=True` sur la dataclass ⇒ toute affectation lève FrozenInstanceError.
        with pytest.raises(dataclasses.FrozenInstanceError):
            slug.value = "autre"  # type: ignore[misc]
