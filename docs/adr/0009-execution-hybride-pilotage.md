# ADR 0009 — Exécution hybride Actions / local pour le pilotage multi-plateformes

- **Statut :** accepté
- **Date :** 2026-08-25

## Contexte

[ADR 0005](0005-scheduler-local-plutot-que-github-actions.md) a tranché : le
pipeline blog s'exécute exclusivement en local (APScheduler), parce que le
bouton ❌ « Garder en local » (ADR 0004) doit écrire le `.mdx` sur le disque de
l'auteur — un runner GitHub Actions, éphémère et sans accès à ce disque, ne
peut pas remplir ce rôle.

Le pilotage multi-plateformes ([ARCHITECTURE.md](../../ARCHITECTURE.md),
[CADRAGE.md](../../CADRAGE.md)) introduit une charge différente : six
pipelines de veille + rédaction, gourmands en appels LLM et en recherche web.
Mais la décision humaine (✅ ✏️ ❌ via les bots Telegram) et l'écriture dans le
calendrier partagé SQLite restent, elles, des opérations locales par nature —
la base vit sur le disque de l'auteur, exactement comme le `.mdx` du blog.

L'argument de l'ADR 0005 (« le runner ne peut pas écrire sur le disque de
l'auteur ») ne s'applique donc qu'à l'étage qui écrit réellement sur ce
disque. Il **ne s'étend pas** à un étage qui ne fait que produire du texte
(veille + rédaction), sans jamais toucher à la base locale.

## Décision

**Exécution hybride, en deux étages :**

| Étage | Où | Pourquoi |
|---|---|---|
| Veille + rédaction des brouillons (6 pipelines) | **GitHub Actions** (gratuit, dépôt public) | Tourne même PC éteint ; ne produit que du texte, aucune écriture sur le disque de l'auteur |
| Bots Telegram, calendrier SQLite, dashboard | **Local** (APScheduler, comme `blogseo`) | La base SQLite et les décisions humaines vivent sur le disque de l'auteur — même raison que l'ADR 0005 |

Ceci **nuance** l'ADR 0005, ne le contredit pas en silence : l'ADR 0005 reste
entièrement vrai pour tout ce qui écrit sur le disque de l'auteur (le
pipeline blog en entier, et l'étage local du pilotage). Il ne s'étendait
jamais à un étage qui ne produit que du texte à transporter — c'est cet
étage-là, et lui seul, que cet ADR déplace vers Actions.

### Le point dur : le transport Actions → local

Un job Actions ne peut pas écrire dans une base SQLite locale. Trois options
sont sur la table (CADRAGE.md, risque n°1) :

| Option | Avantage | Coût |
|---|---|---|
| Actions commite les brouillons en JSON dans le dépôt | Simple, versionné, gratuit | Pollue l'historique Git |
| Actions publie un *artifact* de workflow, le poste local le récupère | Historique Git propre | Le poste doit interroger l'API GitHub ; artifacts conservés 90 jours seulement |
| Actions envoie directement dans Telegram, le bot local écrit en base | Aucun transport de fichier à gérer | Le token de bot devient un secret GitHub — surface d'exposition plus large |

**Aucune des trois n'est tranchée à ce stade.**

### Repli sûr

**Tant que le transport n'est pas choisi, tout tourne en local** — veille,
rédaction, bots, base, dashboard, exactement comme le pipeline blog
aujourd'hui. C'est un système complet et fonctionnel dès le lot 3 : le
passage à Actions pour l'étage veille/rédaction est une optimisation de
charge machine, jamais un prérequis au développement.

## Conséquences

**Positives**
- Le système est utilisable sans jamais résoudre le point dur du transport :
  le repli local est le mode par défaut, pas un mode dégradé provisoire.
- Une fois le transport choisi, l'étage le plus gourmand en appels LLM et en
  recherche web (veille + rédaction) ne consomme plus de disponibilité
  machine locale.

**Négatives**
- Le point dur (transport) reste un problème ouvert : cet ADR documente les
  trois options, il n'en choisit aucune.
- Deux modes d'exécution à maintenir en parallèle (tout-local vs hybride)
  tant que le transport n'est pas tranché, avec le risque que le code du
  mode hybride reste mort si la question n'est jamais résolue.

## Alternatives écartées

**Tout sur Actions, y compris les bots et l'écriture en base**, en committant
l'état de la base SQLite à chaque interaction. Écartée pour deux raisons :
un commit de binaire SQLite à chaque clic ✅/✏️/❌ pollue l'historique bien
plus qu'un JSON de brouillon, et un bot Telegram en long-polling ne peut pas
tourner dans un job Actions borné à 6 h d'exécution.
