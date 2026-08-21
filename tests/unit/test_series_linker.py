"""Tests du maillage retour entre articles d'une série (issue #41)."""

from __future__ import annotations

from blogseo.shared.series_linking import render_series_section, upsert_series_section


class TestInsertionInitiale:
    def test_ajoute_la_section_en_fin_de_corps(self):
        body = "# Titre\n\nContenu de l'article.\n"
        updated = upsert_series_section(body, [("premier-article", "Premier article")])

        assert "## Cette série" in updated
        assert "[Premier article](/blog/premier-article)" in updated
        assert updated.startswith(body.rstrip())

    def test_aucune_entree_ne_modifie_rien(self):
        body = "# Titre\n\nContenu.\n"
        assert upsert_series_section(body, []) == body


class TestMiseAJourIdempotente:
    def test_rejouer_la_meme_liste_ne_duplique_rien(self):
        body = "# Titre\n\nContenu.\n"
        once = upsert_series_section(body, [("a", "Article A")])
        twice = upsert_series_section(once, [("a", "Article A")])

        assert twice == once
        assert once.count("## Cette série") == 1

    def test_ajouter_un_nouvel_episode_remplace_le_bloc_existant(self):
        body = "# Titre\n\nContenu.\n"
        first = upsert_series_section(body, [("a", "Article A")])
        second = upsert_series_section(first, [("a", "Article A"), ("b", "Article B")])

        assert second.count("## Cette série") == 1
        assert "[Article A](/blog/a)" in second
        assert "[Article B](/blog/b)" in second


class TestCoexistenceAvecALireAussi:
    def test_n_interfere_pas_avec_le_a_lire_aussi_du_seo_editor(self):
        body = "# Titre\n\nContenu.\n\n## À lire aussi\n\n- [Autre](/blog/autre)\n"
        updated = upsert_series_section(body, [("a", "Article A")])

        assert "## À lire aussi" in updated
        assert "[Autre](/blog/autre)" in updated
        assert "## Cette série" in updated
        assert "[Article A](/blog/a)" in updated


def test_render_series_section_ordre_preserve():
    section = render_series_section([("un", "Un"), ("deux", "Deux")])
    assert section.index("Un") < section.index("Deux")
