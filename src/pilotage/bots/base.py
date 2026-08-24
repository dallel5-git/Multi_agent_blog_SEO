"""Socle commun des 6 bots de pilotage.

TODO — Lot 4 : factoriser ce qui ne dépend pas de la plateforme — long-polling
`getUpdates` avec offset persisté, clavier inline, retrait du clavier après
clic, garde « un seul chat_id autorisé ».

Réutiliser l'approche déjà validée dans
`blogseo.infrastructure.notifications.telegram` : REST brut via `requests`,
pas d'asyncio, pas de `python-telegram-bot`. **Réutiliser, pas importer** :
la règle d'isolation interdit à `pilotage` d'importer `blogseo`. Si le code
mérite d'être partagé, l'extraire d'abord dans un paquet tiers.
"""
