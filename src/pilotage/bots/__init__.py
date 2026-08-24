"""6 bots Telegram de pilotage PRIVÉS, un par plateforme.

Un token BotFather distinct par bot : recevoir les brouillons YouTube dans le
même fil que les brouillons TikTok rendrait le pilotage illisible, et un token
compromis n'exposerait qu'une seule plateforme.

⚠️ À ne pas confondre avec `TELEGRAM_BOT_TOKEN`, le bot de validation du blog
déjà en service (`blogseo.infrastructure.notifications.telegram`), ni avec la
plateforme « Telegram canal public », qui est une cible de publication et non
un outil de pilotage.

Commandes communes aux 6 bots :

    /en_attente        contenus en attente de validation
    /stats             dernières statistiques de la plateforme
    /publie [lien]     confirme une publication manuelle et enregistre le lien
    boutons inline     ✅ valider · ✏️ corriger · ❌ rejeter
"""
