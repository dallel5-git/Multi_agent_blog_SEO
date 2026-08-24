"""Accès aux données du calendrier partagé.

TODO — Lot 2 : implémenter `CalendarRepository` (sqlite3 de la bibliothèque
standard, aucun ORM à installer) avec au minimum :

    add_item / update_status / list_by_platform / list_pending
    add_post / list_recent_posts
    add_snapshot / latest_snapshot

Points d'attention repris de l'existant `blogseo` :

- écriture atomique et `PRAGMA foreign_keys = ON` à chaque connexion
  (SQLite ne l'active pas par défaut) ;
- aucune requête SQL ailleurs que dans ce fichier ;
- le chemin de la base vient de la configuration, jamais d'une constante.
"""
