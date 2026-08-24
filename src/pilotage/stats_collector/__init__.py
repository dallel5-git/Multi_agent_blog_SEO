"""Agent Collecteur de Statistiques.

Automatique là où une API gratuite existe, saisie manuelle guidée ailleurs :

| Plateforme        | Source                                   | Mode       |
|-------------------|------------------------------------------|------------|
| YouTube           | Data API v3 (10 000 unités/jour)         | auto       |
| Facebook          | Meta Graph API (Page)                    | auto       |
| Instagram         | Meta Graph API (compte Business)         | auto       |
| Telegram (canal)  | Bot API, bot admin du canal              | auto       |
| X                 | aucune API d'engagement gratuite         | **manuel** |
| TikTok            | aucune API d'engagement gratuite         | **manuel** |

Toute mesure atterrit dans `stat_snapshots`, quelle que soit son origine :
le tableau de bord n'a pas à savoir si le chiffre vient d'une API ou du clavier.
"""
