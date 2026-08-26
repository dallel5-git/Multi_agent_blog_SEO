"""Point d'entrée de l'application Streamlit — tableau de bord de pilotage.

Lancer :

    streamlit run src/pilotage/dashboard/app.py
    make dashboard-pilotage

Trois onglets, alimentés en lecture seule par `shared_calendar.repository` :

    1. Kanban        — pipeline de contenu par plateforme
    2. Statistiques   — évolution dans le temps, par plateforme
    3. Conversions    — clics d'affiliation et ventes, par plateforme d'origine

**Lecture seule** : aucune écriture en base, aucune génération de contenu,
aucun appel LLM — c'est le contrat du Lot 6 (CADRAGE.md).

⚠️ À ne pas confondre avec `blogseo dashboard`, qui génère une page HTML
statique des runs du pipeline blog. Les deux coexistent sans se connaître.
"""

from __future__ import annotations

import streamlit as st

from ..brand_kernel.loader import load_brand_kernel
from ..brand_kernel.schema import BrandKernel
from ..config.settings import PilotageSettings
from ..shared_calendar.repository import CalendarRepository
from .views import conversions, kanban, stats

st.set_page_config(page_title="Pilotage — tableau de bord", page_icon="📊", layout="wide")


def _load_brand_kernel_safely() -> BrandKernel | None:
    """La vue Conversions se dégrade proprement si le Brand Kernel ne charge
    pas (ex. TODO réapparu) : ce n'est pas au tableau de bord de planter pour
    un problème qui relève du Lot 1."""
    try:
        return load_brand_kernel()
    except (FileNotFoundError, ValueError):
        return None


def main() -> None:
    st.title("📊 Pilotage multi-plateformes")

    settings = PilotageSettings.from_env()
    if not settings.calendar.db_path.exists():
        st.warning(
            f"Base introuvable : `{settings.calendar.db_path}`\n\n"
            "Lancez `pilotage migrate` pour créer le calendrier partagé."
        )
        return

    repository = CalendarRepository(settings.calendar.db_path)
    kernel = _load_brand_kernel_safely()

    onglet_kanban, onglet_stats, onglet_conversions = st.tabs(
        ["📋 Kanban", "📈 Statistiques", "💰 Conversions"]
    )
    with onglet_kanban:
        kanban.render(repository)
    with onglet_stats:
        stats.render(repository)
    with onglet_conversions:
        conversions.render(repository, kernel)


main()
