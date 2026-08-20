# ADR 0005 — Planification locale (APScheduler), pas GitHub Actions

- **Statut :** accepté
- **Date :** 2026-08-19

## Contexte

Le prompt initial laissait le choix entre GitHub Actions (cron) et un
planificateur Python, en demandant un choix argumenté. GitHub Actions est
gratuit et illimité sur dépôt public, et ne demande aucune machine allumée.

## Décision

**Le pipeline s'exécute sur la machine de l'auteur, planifié par APScheduler
(ou un timer systemd utilisateur).**

Raison décisive : la règle ❌ « Garder en local » (ADR 0004) impose d'écrire le
`.mdx` dans `/home/oussama/.../oussama-blog/content/articles`. Un runner GitHub
Actions tourne dans un conteneur jetable dans le cloud : il n'a aucun accès à ce
disque. Le pipeline doit donc s'exécuter là où vivent les fichiers.

Raisons secondaires :

- le modèle d'embeddings (~90 Mo) reste en cache local au lieu d'être
  retéléchargé à chaque run ;
- la base ChromaDB persiste entre les runs sans artefact CI à gérer ;
- une attente Telegram de 24 h ne consomme aucune minute CI et ne se heurte pas
  à la limite de 6 h par job.

Un workflow GitHub Actions est tout de même fourni, mais **pour les tests et le
lint uniquement**, pas pour la publication.

## Conséquences

**Positives**
- Le comportement ❌ est possible, ce qui est le cœur du besoin.
- Zéro minute CI consommée par les runs de production.

**Négatives**
- La machine doit être allumée à l'heure du déclenchement. Mitigé par
  `misfire_grace_time=3600` et `coalesce=True` : un run manqué se rattrape au
  démarrage suivant plutôt que de s'exécuter cinq fois d'affilée.
- `loginctl enable-linger` est nécessaire pour que le timer tourne hors session
  graphique. Automatisé par `scripts/install_systemd_timer.sh`.

## Alternative conservée pour plus tard

Si le besoin de ❌ disparaissait (publication systématique), GitHub Actions
deviendrait le meilleur choix : le workflow n'aurait qu'à appeler
`blogseo run --no-human-review` avec les secrets du dépôt.
