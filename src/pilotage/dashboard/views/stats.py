"""Vue « Statistiques » du tableau de bord — séries temporelles par plateforme.

Construite depuis `stat_snapshots`, qui ACCUMULE (jamais n'écrase) : c'est ce
qui permet de tracer une courbe plutôt qu'un chiffre isolé. `source='manual'`
(X, TikTok) est visuellement distinguée de `source='api'`.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from ...shared_calendar.repository import CalendarRepository
from ..data import stats_series_by_platform

_PERIODES: dict[str, int | None] = {
    "7 derniers jours": 7,
    "30 derniers jours": 30,
    "90 derniers jours": 90,
    "Tout l'historique": None,
}


def render(repository: CalendarRepository) -> None:
    choix_periode = st.selectbox("Période", options=list(_PERIODES), index=1)
    jours = _PERIODES[choix_periode]
    depuis = (date.today() - timedelta(days=jours)).isoformat() if jours else None

    series_par_plateforme = stats_series_by_platform(repository, since=depuis)

    au_moins_une_serie = any(serie.has_data for serie in series_par_plateforme.values())
    if not au_moins_une_serie:
        st.info(
            "Aucune statistique enregistrée pour l'instant. "
            "`pilotage collect-stats <plateforme>` (automatique) ou `/mesure` "
            "dans les bots (X, TikTok) alimentent cette vue."
        )
        return

    for platform, serie in series_par_plateforme.items():
        if not serie.has_data:
            continue

        st.subheader(platform.label)
        if serie.has_manual_data:
            st.caption("📝 Contient des mesures saisies à la main (source = manual)")

        lignes = [
            {
                "captured_at": snapshot.captured_at,
                "vues": snapshot.views or 0,
                "likes": snapshot.likes or 0,
                "abonnés": snapshot.followers or 0,
                "source": snapshot.source.value,
            }
            for snapshot in serie.snapshots
        ]
        st.dataframe(lignes, use_container_width=True, hide_index=True)

        vues = [ligne["vues"] for ligne in lignes if ligne["vues"]]
        if vues:
            st.line_chart({"vues": vues})
