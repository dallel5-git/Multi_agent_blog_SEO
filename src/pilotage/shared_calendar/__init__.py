"""Calendrier partagé — connexion inter-plateforme légère et OPTIONNELLE.

Une base SQLite unique (aucun serveur, aucun compte, donc gratuite) que chaque
pipeline **peut** consulter pour proposer une mention croisée vers un contenu
déjà publié ailleurs. Consulter est facultatif ; la suggestion produite est
toujours validée à la main via le bot Telegram de la plateforme concernée.

Ce module ne crée **aucune** dépendance éditoriale entre les plateformes :
chaque pipeline garde sa veille, ses sujets et son calendrier propres.

Trois tables, décrites dans `schema.sql` :

    content_items   — une idée / un contenu, quelle que soit la plateforme
    platform_posts  — une publication réelle, avec son lien et sa date
    stat_snapshots  — une mesure d'audience à un instant t
"""

from __future__ import annotations

from .blog_bridge import sync_blog_articles
from .migrate import apply_schema
from .models import ContentItem, ContentStatus, CrossRefState, PlatformPost, StatSnapshot, StatSource
from .repository import CalendarRepository

__all__ = [
    "apply_schema",
    "sync_blog_articles",
    "CalendarRepository",
    "ContentItem",
    "ContentStatus",
    "CrossRefState",
    "PlatformPost",
    "StatSnapshot",
    "StatSource",
]
