# ADR 0004 — Validation Telegram : ✅ pousse, ❌ écrit en local

- **Statut :** accepté
- **Date :** 2026-08-19

## Contexte

Le blog est déployé sur Vercel depuis un dépôt GitHub : tout `push` sur `main`
met le site en ligne. Publier automatiquement un article généré par IA sans
relecture est un risque éditorial que le propriétaire refuse.

Question tranchée avec le propriétaire : que doit faire exactement chaque bouton ?

## Décision

Trois boutons inline sur Telegram, avec une sémantique sans ambiguïté :

| Bouton | Fichier écrit dans `content/articles/` | `git commit` | `git push` |
|---|---|---|---|
| ✅ Publier | oui | oui | oui → Vercel déploie |
| ❌ Garder en local | **oui** | non | non |
| 🔁 Faire réécrire | non | non | non |

Points complémentaires :

- Un brouillon est **toujours** écrit dans `storage/drafts/` avant la demande de
  décision, quelle que soit la réponse.
- Absence de réponse dans les 24 h → comportement de ❌ (`TELEGRAM_DEFAULT_ON_TIMEOUT=reject`).
- Telegram non configuré → comportement de ❌.
- `HUMAN_REVIEW=false` → publication automatique, réservé à un usage averti.
- `--dry-run` → uniquement le brouillon ; le dossier du blog n'est jamais touché.

## Conséquences

**Positives**
- Aucun article ne part en ligne sans un clic humain explicite.
- Le refus reste productif : le fichier est prêt, il ne reste qu'à relire et pousser.
- Le comportement par défaut en cas de panne est toujours le plus sûr.

**Négatives**
- Le pipeline reste bloqué jusqu'à 24 h en attente d'une réponse. Acceptable pour
  un run chaque semaine sur une machine personnelle.
- Un `getUpdates` concurrent (autre process, webhook) volerait le callback. Documenté
  dans le README.

## Implémentation

`application/agents/publisher.py`, couvert par
`tests/unit/test_publisher_decision.py` (10 cas : les 3 boutons, dry-run,
expiration du délai, absence de dépôt Git, push refusé, `HUMAN_REVIEW=false`).
