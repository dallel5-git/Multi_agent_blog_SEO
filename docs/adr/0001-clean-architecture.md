# ADR 0001 — Clean Architecture en quatre couches

- **Statut :** accepté
- **Date :** 2026-08-19

## Contexte

Le projet doit rester modifiable dans la durée par une seule personne : ajouter
ou retirer un agent, changer de LLM quand un free tier disparaît, brancher
Search Console plus tard. Une organisation « un fichier par agent avec les
appels API dedans » aurait été plus rapide à écrire, mais chaque changement de
fournisseur aurait touché les neuf agents.

## Décision

Quatre couches, avec une règle de dépendance stricte vers l'intérieur :

- `domain/` — entités, value objects, **ports** (interfaces). Aucune dépendance,
  pas même `requests`.
- `application/` — les agents et les cas d'usage. Ne connaissent que les ports.
- `infrastructure/` — les adapters concrets qui implémentent les ports.
- `interfaces/` — CLI et planificateur.

Le câblage se fait dans un unique *composition root* :
`infrastructure/config/container.py`.

## Conséquences

**Positives**
- Le Quality Gate est testable sans réseau ni clé (aucun LLM dedans).
- Le mode `--offline` se résume à injecter `FakeLLM` à la place de la chaîne réelle.
- Remplacer Gemini, DuckDuckGo ou Telegram ne touche qu'un fichier.
- 125 tests unitaires tournent en moins d'une seconde, sans réseau.

**Négatives**
- Plus de fichiers et plus de code d'assemblage qu'une approche directe.
- Une couche d'indirection à comprendre avant de contribuer.

**Neutres**
- La règle de dépendance est vérifiable mécaniquement :
  `grep -r "infrastructure" src/blogseo/domain/` doit ne rien renvoyer.

## Alternatives écartées

- **Script monolithique** : plus rapide au départ, ingérable pour les tests et
  les modes dégradés.
- **Architecture hexagonale « pure »** avec un module par bounded context :
  surdimensionné pour un projet à un seul flux métier.
