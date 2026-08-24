"""Entités Python du calendrier partagé (miroir des tables de `schema.sql`).

TODO — Lot 2 : définir `ContentItem`, `PlatformPost`, `StatSnapshot` en
dataclasses gelées, plus les énumérations d'état :

    ContentStatus : idea → drafted → pending_review → approved → published → archived
    (`rejected` est un état terminal, atteignable depuis `pending_review`)

Ces états sont exactement les colonnes du Kanban du tableau de bord.
"""
