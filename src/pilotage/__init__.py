"""`pilotage` — système de pilotage multi-plateformes.

Paquet **frère** de `blogseo`, volontairement séparé : le pipeline blog
existant continue de tourner sans rien connaître de ce module.

Règle d'isolation (vérifiée par `tests/unit/test_pilotage_scaffolding.py`) :

- `pilotage` n'importe **jamais** `blogseo` ;
- `blogseo` n'importe **jamais** `pilotage`.

Le seul point de contact est la base SQLite partagée (`shared_calendar/`),
alimentée pour le blog par un pont écrit à part, jamais par un import croisé.

Sous-modules :

| Module            | Rôle |
|-------------------|------|
| `brand_kernel`    | Identité de marque partagée par TOUS les rédacteurs |
| `shared_calendar` | Base SQLite : `content_items`, `platform_posts`, `stat_snapshots` |
| `pipelines`       | 6 pipelines de contenu indépendants, un par plateforme |
| `bots`            | 6 bots Telegram de pilotage privés, un par plateforme |
| `stats_collector` | Collecte des statistiques (automatique ou saisie guidée) |
| `dashboard`       | Application Streamlit locale (Kanban, stats, conversions) |
| `config`          | Lecture de l'environnement, sur le modèle de `blogseo.…config.settings` |

**État : squelette.** Aucun module ne contient encore de logique métier.
Voir `CADRAGE.md` à la racine du dépôt pour le découpage en lots.
"""
