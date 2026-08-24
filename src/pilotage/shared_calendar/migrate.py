"""Application du schéma SQL à la base du calendrier partagé.

TODO — Lot 2 : implémenter

    def apply_schema(db_path: Path) -> None: ...

qui exécute `schema.sql` via `sqlite3.Connection.executescript()`. Le script
est écrit en `CREATE TABLE IF NOT EXISTS`, donc rejouable sans risque.

Prévoir une commande CLI `pilotage migrate` une fois le module `config` en
place, sur le modèle des sous-commandes de `blogseo.interfaces.cli`.
"""
