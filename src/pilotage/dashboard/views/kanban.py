"""Vue « Kanban » du tableau de bord — pipeline de contenu par plateforme.

Colonnes = les sept états de `ContentStatus` (`idea` → `archived`), lignes =
les plateformes. Lecture seule : valider un contenu se fait dans le bot
Telegram de la plateforme, jamais ici.
"""

from __future__ import annotations

import streamlit as st

from ...shared_calendar.models import ContentStatus
from ...shared_calendar.repository import CalendarRepository
from ..data import kanban_board, kanban_counts

_STATUS_LABELS: dict[ContentStatus, str] = {
    ContentStatus.IDEA: "💡 Idée",
    ContentStatus.DRAFTED: "📝 Rédigé",
    ContentStatus.PENDING_REVIEW: "⏳ En attente",
    ContentStatus.APPROVED: "✅ Approuvé",
    ContentStatus.PUBLISHED: "🚀 Publié",
    ContentStatus.REJECTED: "❌ Rejeté",
    ContentStatus.ARCHIVED: "🗄 Archivé",
}


def render(repository: CalendarRepository) -> None:
    board = kanban_board(repository)
    counts = kanban_counts(board)

    plateformes = list(board)
    choix = st.multiselect(
        "Filtrer par plateforme",
        options=[p.value for p in plateformes],
        default=[p.value for p in plateformes],
        format_func=lambda value: next(p.label for p in plateformes if p.value == value),
    )
    plateformes_retenues = [p for p in plateformes if p.value in choix]

    if not plateformes_retenues:
        st.info("Aucune plateforme sélectionnée.")
        return

    colonnes = st.columns(len(ContentStatus))
    for colonne, status in zip(colonnes, ContentStatus, strict=True):
        with colonne:
            st.markdown(f"**{_STATUS_LABELS[status]}** ({counts[status]})")
            for platform in plateformes_retenues:
                items = board[platform][status]
                if not items:
                    continue
                st.caption(platform.label)
                for item in items:
                    st.markdown(f"- #{item.id} {item.title}")

    if all(counts[status] == 0 for status in ContentStatus):
        st.info("Aucun contenu dans le calendrier pour l'instant.")
