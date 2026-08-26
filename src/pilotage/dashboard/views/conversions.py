"""Vue « Conversions » du tableau de bord — clics d'affiliation et ventes,
ventilés par plateforme d'ORIGINE.

CADRAGE.md risque n°6 : cette vue n'affiche que ce qui a été enregistré, et
dépend du paramètre de suivi des liens (décision n°6, Brand Kernel). Sans
mécanisme de capture, un zéro ne veut rien dire — `data.tracking_caveat()`
le rappelle explicitement plutôt que de laisser croire à zéro conversion.
"""

from __future__ import annotations

import streamlit as st

from ...brand_kernel.schema import BrandKernel
from ...shared_calendar.repository import CalendarRepository
from ..data import conversions_by_platform, tracking_caveat


def render(repository: CalendarRepository, kernel: BrandKernel | None) -> None:
    caveat = tracking_caveat(kernel)
    if caveat:
        st.warning(caveat)

    resume = conversions_by_platform(repository)
    total_clics = sum(r.affiliate_clicks for r in resume)
    total_ventes = sum(r.sales for r in resume)
    total_revenu = sum(r.revenue_tnd for r in resume)

    if total_clics == 0 and total_ventes == 0 and total_revenu == 0:
        st.info("Aucune conversion enregistrée pour l'instant.")

    colonnes = st.columns(3)
    colonnes[0].metric("Clics d'affiliation", total_clics)
    colonnes[1].metric("Ventes", total_ventes)
    colonnes[2].metric("Chiffre d'affaires (TND)", f"{total_revenu:.2f}")

    st.dataframe(
        [
            {
                "Plateforme": r.platform.label,
                "Clics d'affiliation": r.affiliate_clicks,
                "Ventes": r.sales,
                "Revenu (TND)": r.revenue_tnd,
            }
            for r in resume
        ],
        use_container_width=True,
        hide_index=True,
    )
