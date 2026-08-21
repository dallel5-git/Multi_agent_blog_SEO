---
name: 🐛 Anomalie
about: Signaler un comportement inattendu du pipeline
title: "[BUG] "
labels: bug
---

## Ce qui se passe

<!-- Décrivez le comportement observé -->

## Ce qui devrait se passer

## Comment reproduire

1.
2.

## Contexte

- Commande lancée : `blogseo ...`
- `run_id` concerné (voir `blogseo runs`) :
- Agent concerné (si connu) :
- Version de Python :
- LLM utilisé au moment de l'erreur (cerebras / groq / fake) :

## Logs

<details>
<summary>Extrait de storage/logs/pipeline.log</summary>

```
(collez ici, EN AYANT RETIRÉ TOUTE CLÉ D'API)
```

</details>

## Vérifications

- [ ] J'ai relu `MEMOIRE.md` § « Pièges déjà rencontrés »
- [ ] J'ai lancé `blogseo check`
- [ ] J'ai vérifié qu'aucune clé d'API n'apparaît dans les logs collés
