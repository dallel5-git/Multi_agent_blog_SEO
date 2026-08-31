# Backlog — Multi_agent_blog_SEO

> Dépôt : https://github.com/dallel5-git/Multi_agent_blog_SEO
>
> **Note de statut (août 2026).** Ce document est l'historique du backlog
> initial. Les issues #31 à #36 ont depuis été implémentées (Search Console,
> sources tunisiennes, dashboards, Social Writer, séries et régénération).
> Pour le travail restant du pilotage multi-plateformes et sa mise en service,
> consulter [`../CADRAGE.md`](../CADRAGE.md).
>
> Ce backlog est découpé en **8 epics** et **32 issues**. Les issues marquées
> ✅ correspondent au périmètre déjà livré en v1.0.0 : elles sont créées puis
> fermées immédiatement par le script, pour que l'historique du dépôt reflète
> le travail réel et serve de documentation.
>
> Pour créer tout cela en une commande :
> ```bash
> gh auth login
> ./scripts/create_github_issues.sh
> ```

---

## Conventions

**Labels**

| Label | Couleur | Sens |
|---|---|---|
| `epic` | `#5319e7` | Regroupement de plusieurs issues |
| `agent` | `#0e8a16` | Touche un des 9 agents |
| `infra` | `#1d76db` | Adapter, configuration, CI |
| `domain` | `#fbca04` | Entité, value object, port |
| `docs` | `#c5def5` | Documentation |
| `test` | `#bfd4f2` | Tests |
| `bug` | `#d73a4a` | Anomalie |
| `enhancement` | `#a2eeef` | Amélioration |
| `seo` | `#e99695` | Qualité SEO du contenu |
| `free-tier` | `#fef2c0` | Contrainte « zéro coût » |
| `v1` | `#0052cc` | Livré en v1.0.0 |
| `v1.1` | `#006b75` | Prochaine itération |
| `backlog` | `#ededed` | Non planifié |

**Milestones**

| Milestone | Contenu |
|---|---|
| `v1.0 — Pipeline opérationnel` | Les 9 agents, l'orchestration, la validation Telegram, les tests |
| `v1.1 — Qualité & mesure` | Search Console, sources tunisiennes, tableau de bord |
| `v2.0 — Diffusion` | Réseaux sociaux, newsletter, séries d'articles |

**Format des issues** : contexte → tâches → critères d'acceptation → estimation.

---

## EPIC 1 — Socle & architecture ✅

> Poser la Clean Architecture, les entités et les ports.

### #1 ✅ Mettre en place la Clean Architecture en 4 couches
**Contexte** — Le projet doit rester modifiable dans la durée : changer de LLM,
ajouter un agent, brancher Search Console plus tard.
**Tâches**
- [x] Créer `domain/`, `application/`, `infrastructure/`, `interfaces/`
- [x] Définir la règle de dépendance vers l'intérieur
- [x] Créer le composition root `infrastructure/config/container.py`
**Critères d'acceptation**
- `grep -r "infrastructure" src/blogseo/domain/` ne renvoie rien
- `grep -r "infrastructure" src/blogseo/application/` ne renvoie rien
**Estimation** : 5 pts · **Labels** : `epic`, `domain`, `v1`

### #2 ✅ Modéliser les entités et value objects du domaine
**Tâches**
- [x] `Article` avec sérialisation `.mdx` et mesures (mots, H2, densité)
- [x] `Topic`, `TrendItem`/`TrendDigest`, `ReviewResult`, `PipelineRun`
- [x] `Slug`, `Category`, `SeoMetadata`, `QualityReport`
**Critères d'acceptation**
- `Slug.from_title()` gère accents, ponctuation, mots vides et troncature
- `Category.coerce()` ramène toujours une valeur de l'union fermée du blog
- Le `.mdx` produit est relu sans erreur par le parseur de frontmatter
**Estimation** : 5 pts · **Labels** : `domain`, `v1`

### #3 ✅ Définir tous les ports (interfaces abstraites)
**Tâches**
- [x] `LLMPort`, `SearchPort`, `TrendsPort`, `TechSourcePort`, `EmbeddingPort`
- [x] `ArticleHistoryPort`, `ArticleSourcePort`, `RunRepositoryPort`
- [x] `ArticleWriterPort`, `GitPublisherPort`, `ImageGeneratorPort`
- [x] `NotifierPort`, `HumanReviewPort`, `AnalyticsPort`
**Critères d'acceptation** — chaque port a au moins deux implémentations
**Estimation** : 3 pts · **Labels** : `domain`, `v1`

### #4 ✅ Configuration par variables d'environnement, zéro clé en dur
**Tâches**
- [x] `Settings.from_env()` avec sections typées
- [x] `.env.example` documenté service par service
- [x] `Settings.describe()` n'affiche jamais une clé
**Critères d'acceptation** — `grep -rE "AIza|gsk_|sk-" src/` ne renvoie que des motifs de détection
**Estimation** : 2 pts · **Labels** : `infra`, `v1`

---

## EPIC 2 — Adapters gratuits ✅

> Implémenter les ports avec des services 100 % free tier.

### #5 ✅ Adapter LLM Gemini free tier
**Tâches** — appel REST direct, détection du 429, extraction robuste du texte, safety settings desserrés
**Critères d'acceptation** — un 429 lève `QuotaExceededError`, pas une erreur générique
**Estimation** : 3 pts · **Labels** : `infra`, `free-tier`, `v1`

### #6 ✅ Adapter LLM Groq free tier + chaîne de fallback
**Tâches**
- [x] Adapter Groq (API compatible OpenAI, appelée en REST brut)
- [x] `FallbackLLM` : bascule immédiate sur quota, retry sur panne réseau
- [x] Statistiques d'usage par fournisseur
**Critères d'acceptation** — 8 tests unitaires couvrant tous les scénarios de bascule
**Estimation** : 3 pts · **Labels** : `infra`, `free-tier`, `v1`

### #7 ✅ Rate limiter double fenêtre persisté
**Contexte** — Gemini plafonne à ~15 req/min et ~1500/jour. Il faut bloquer avant l'appel.
**Critères d'acceptation**
- Le quota journalier survit à un redémarrage du process
- Quota épuisé → `acquire()` renvoie `False` (bascule) plutôt que d'attendre
**Estimation** : 3 pts · **Labels** : `infra`, `free-tier`, `v1`

### #8 ✅ Recherche web : DuckDuckGo + Tavily en repli
**Tâches** — throttling anti-ban, compatibilité `ddgs`/`duckduckgo-search`, cascade
**Estimation** : 2 pts · **Labels** : `infra`, `free-tier`, `v1`

### #9 ✅ Sources de veille publiques
**Tâches** — Hacker News (Firebase), Reddit (`.json` + User-Agent), dev.to, RSS générique
**Critères d'acceptation** — une source morte ne fait jamais échouer le run
**Estimation** : 3 pts · **Labels** : `infra`, `free-tier`, `v1`

### #10 ✅ Anti-doublon : embeddings locaux + ChromaDB
**Tâches** — `sentence-transformers` CPU, ChromaDB SQLite, repli hachage + index JSON
**Critères d'acceptation** — un quasi-doublon obtient un score > 0.85, un sujet neuf < 0.5
**Estimation** : 5 pts · **Labels** : `infra`, `free-tier`, `v1`

### #11 ✅ Image de couverture Pollinations + repli Pillow
**Critères d'acceptation** — Pollinations indisponible → image locale générée, jamais d'échec du run
**Estimation** : 2 pts · **Labels** : `infra`, `free-tier`, `v1`

---

## EPIC 3 — Les 9 agents ✅

### #12 ✅ Agent 1 — Trend Scout (veille mondiale)
**Estimation** : 3 pts · **Labels** : `agent`, `v1`

### #13 ✅ Agent 2 — Tunisia Watcher (veille locale)
**Contexte** — L'angle tunisien est l'ADN éditorial du blog : il faut de la matière locale réelle.
**Critères d'acceptation** — le LLM ne peut citer que des faits présents dans les résultats fournis (`coverage_gap` si vide)
**Estimation** : 3 pts · **Labels** : `agent`, `v1`

### #14 ✅ Agent 3 — Keyword Analyst avec anti-doublon
**Critères d'acceptation** — 3 tentatives maximum, température croissante, `DuplicateTopicError` explicite en cas d'échec
**Estimation** : 5 pts · **Labels** : `agent`, `seo`, `v1`

### #15 ✅ Agent 4 — Content Writer (rédaction + révision)
**Critères d'acceptation** — pas de frontmatter parasite, pas de H1, mode révision distinct du mode rédaction
**Estimation** : 5 pts · **Labels** : `agent`, `v1`

### #16 ✅ Agent 5 — Technical Reviewer
**Tâches** — vérification HTTP réelle des liens, détection de secrets en clair, relecture LLM du code
**Estimation** : 3 pts · **Labels** : `agent`, `v1`

### #17 ✅ Agent 6 — SEO Editor
**Critères d'acceptation** — un slug interne inventé par le LLM est retiré, les longueurs sont corrigées automatiquement
**Estimation** : 3 pts · **Labels** : `agent`, `seo`, `v1`

### #18 ✅ Agent 7 — Quality Gate 100 % déterministe
**Critères d'acceptation** — aucun appel LLM, 20 contrôles, consignes de révision structurées
**Estimation** : 5 pts · **Labels** : `agent`, `test`, `v1`

### #19 ✅ Agent 8 — Publisher avec validation Telegram
**Estimation** : 5 pts · **Labels** : `agent`, `v1`

### #20 ✅ Agent 9 — Analytics Tracker (stub) + réindexation
**Estimation** : 2 pts · **Labels** : `agent`, `v1`

---

## EPIC 4 — Orchestration ✅

### #21 ✅ Graphe LangGraph avec deux boucles de feedback
**Critères d'acceptation** — `blogseo graph` produit un Mermaid correct montrant les deux boucles
**Estimation** : 5 pts · **Labels** : `infra`, `v1`

### #22 ✅ Exécuteur séquentiel de secours
**Contexte** — LangGraph absent ne doit jamais bloquer le pipeline.
**Critères d'acceptation** — les deux exécuteurs partagent la même description de topologie
**Estimation** : 2 pts · **Labels** : `infra`, `v1`

### #23 ✅ Gestion d'erreurs, retry et modes dégradés
**Critères d'acceptation** — tableau des pannes documenté dans `docs/ARCHITECTURE.md`, chaque ligne vérifiée
**Estimation** : 3 pts · **Labels** : `infra`, `v1`

---

## EPIC 5 — Publication & validation humaine ✅

### #24 ✅ Bot Telegram à trois boutons
**Critères d'acceptation**
- ✅ → écriture + commit + push ; ❌ → écriture seule ; 🔁 → retour au rédacteur
- Le clavier est retiré après le clic (pas de double décision)
- L'offset `getUpdates` est persisté
**Estimation** : 5 pts · **Labels** : `agent`, `infra`, `v1`

### #25 ✅ Écriture `.mdx` atomique et publication Git ciblée
**Critères d'acceptation** — jamais de `git add -A`, jamais d'écrasement d'un article existant
**Estimation** : 3 pts · **Labels** : `infra`, `v1`

### #26 ✅ Mode `--dry-run` et mode `--offline`
**Estimation** : 2 pts · **Labels** : `infra`, `test`, `v1`

---

## EPIC 6 — Automatisation & exploitation ✅

### #27 ✅ Planificateur local 48 h + timer systemd
**Estimation** : 3 pts · **Labels** : `infra`, `v1`

### #28 ✅ CLI complète et journalisation
**Tâches** — `run`, `check`, `index`, `graph`, `runs`, `show` ; logs console colorés + fichier rotatif
**Estimation** : 3 pts · **Labels** : `infra`, `v1`

---

## EPIC 7 — Tests & documentation ✅

### #29 ✅ Tests unitaires des fonctions critiques
**Critères d'acceptation** — Quality Gate, anti-doublon, parsing SEO, fallback LLM, rate limiter, routage, décision Publisher, contrôle de langue
**Estimation** : 5 pts · **Labels** : `test`, `v1`

### #30 ✅ README, MEMOIRE.md, ARCHITECTURE.md et ADR
**Estimation** : 3 pts · **Labels** : `docs`, `v1`

---

## EPIC 8 — Évolutions (non livrées)

### #31 Brancher Google Search Console sur `AnalyticsPort`
**Contexte** — Le port et l'agent 9 sont prêts ; il ne manque que l'adapter.
**Tâches**
- [ ] Adapter `SearchConsoleAnalytics` (OAuth, API gratuite)
- [ ] Mapper les requêtes réelles vers `PerformanceFeedback`
- [ ] Injecter le feedback dans le prompt du Keyword Analyst
**Critères d'acceptation**
- Aucune modification des agents existants
- Les mots-clés en position 11-30 remontent comme pistes de sujets
**Estimation** : 5 pts · **Labels** : `enhancement`, `agent`, `seo`, `v1.1`

### #32 Enrichir les sources tunisiennes
**Tâches** — identifier 3 à 5 flux RSS de médias tech tunisiens fiables, les documenter dans `.env.example`, mesurer l'apport
**Critères d'acceptation** — le champ `coverage_gap` du Tunisia Watcher devient vide sur 3 runs consécutifs
**Estimation** : 3 pts · **Labels** : `enhancement`, `agent`, `v1.1`

### #33 Tableau de bord HTML local des runs
**Tâches** — page statique générée depuis `storage/runs/*.json` : historique, scores qualité, décisions, durées
**Estimation** : 3 pts · **Labels** : `enhancement`, `v1.1`

### #34 Agent 10 — Social Writer
**Contexte** — Un post LinkedIn et un thread X générés à partir de l'article publié.
**Critères d'acceptation** — s'ajoute sans modifier les 9 agents existants (preuve de la modularité)
**Estimation** : 5 pts · **Labels** : `enhancement`, `agent`, `v2.0`

### #35 Mode « série d'articles »
**Contexte** — Produire une série de 3 à 5 articles liés entre eux, avec maillage interne croisé.
**Estimation** : 8 pts · **Labels** : `enhancement`, `seo`, `v2.0`

### #36 Régénération d'articles sous-performants
**Contexte** — Les articles avec beaucoup d'impressions et peu de clics méritent une réécriture ciblée du titre et de la description.
**Estimation** : 5 pts · **Labels** : `enhancement`, `seo`, `v2.0`
