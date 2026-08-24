"""Configuration `pilotage`, sur le modèle de `blogseo.infrastructure.config.settings`.

TODO — Lot 2 : implémenter `PilotageSettings.from_env()` avec les sections :

    - `bots`      : les 6 tokens BotFather + les 6 chat_id (voir `.env.example`)
    - `calendar`  : chemin de la base SQLite (défaut `storage/pilotage/calendar.db`)
    - `youtube`   : clé Data API v3 + identifiant de chaîne
    - `meta`      : token de page longue durée, page_id, instagram_business_id
    - `dashboard` : port Streamlit, ouverture automatique du navigateur

RÈGLE ABSOLUE, identique au reste du projet : aucune clé en dur, jamais.
`describe()` affiche « configurée / absente », jamais la valeur.
"""
