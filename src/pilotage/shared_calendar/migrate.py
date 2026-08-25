"""Application du schéma SQL à la base du calendrier partagé.

`schema.sql` est écrit en `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT
EXISTS` / `CREATE VIEW IF NOT EXISTS` : rejouer la migration ne casse rien
(voir `tests/unit/test_pilotage_scaffolding.py::test_le_schema_est_rejouable`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "schema.sql"


def apply_schema(db_path: Path) -> None:
    """Crée le dossier parent si besoin, puis applique `schema.sql`."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(schema_sql)
        connection.commit()
    finally:
        connection.close()
